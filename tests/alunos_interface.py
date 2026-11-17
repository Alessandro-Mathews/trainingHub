"""TH-31: delivered JavaScript/DOM behavior and isolated real HTTP contracts.

Node is required for the critical lossless-ID checks. No browser/npm dependency.
Visual, focus-trap and layout acceptance is separate: interface_web.py --browser.
"""

from contextlib import closing
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
from auth_fixture import insert_admin, login_client

ROOT = Path(__file__).resolve().parents[1]


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = {"tag": "document", "attrs": {}, "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in {"input", "img", "link", "meta", "br", "hr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_data(self, data):
        self.stack[-1]["children"].append(data)


JS = r'''
import nativeAssert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
let checks = 0;
const assert = new Proxy(nativeAssert, {
  apply(target, self, args) { checks++; return Reflect.apply(target, self, args); },
  get(target, key) { const value = target[key]; return typeof value === 'function'
    ? (...args) => { checks++; return value(...args); } : value; },
});
const markup = __MARKUP__;
const source = await readFile('public/js/api.js', 'utf8');
const apiURL = 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const api = await import(apiURL);
const response = (body, status = 200) => new Response(body, { status });
const limits = ['1', '1099511627776', '9007199254740993', '9223372036854775807'];
const bodies = [];
for (const id of limits) {
  globalThis.fetch = async () => response(`{"userId":${id},"academiaId":${id},"perfilId":${id}}`);
  assert.deepEqual(await api.getAuthContext(), {userId:id, academiaId:id, perfilId:id});
  for (const key of ['id','academia_id','perfil_id','usuario_id','instrutor_id','aluno_id']) {
    assert.equal(api.parseJson(`[{"nested":{"${key}":${id}}}]`)[0].nested[key], id);
  }
  const body = api.serializeBody({usuario_id:id});
  assert.equal(body, `{"usuario_id":${id}}`);
  assert.equal(api.serializeBody({academia_id:id,perfil_id:id}), `{"academia_id":${id},"perfil_id":${id}}`);
  assert.equal(new Map([[id, 'exact']]).get(api.parseJson(`{"id":${id}}`).id), 'exact');
  bodies.push(body);
  const sent=[];
  globalThis.fetch=async(url,options)=>{sent.push({url,...options});return response(`{"id":${id}}`);};
  await api.postJson('/api/usuarios',{academia_id:id,perfil_id:id,nome:'Nome',email:'a@b',senha:'secret'});
  assert.equal(sent.at(-1).body,`{"academia_id":${id},"perfil_id":${id},"nome":"Nome","email":"a@b","senha":"secret"}`);
  await api.postJson('/api/alunos',{usuario_id:id});assert.equal(sent.at(-1).body,`{"usuario_id":${id}}`);
  await api.putJson(`/api/usuarios/${id}`,{nome:'Nome',email:'a@b'});
  assert.equal(sent.at(-1).url,`/api/usuarios/${id}`);
  assert.equal(sent.at(-1).body,'{"nome":"Nome","email":"a@b"}');
  await api.putJson(`/api/usuarios/${id}/status`,{ativo:false});assert.equal(sent.at(-1).body,'{"ativo":false}');
}
for (const input of ['0','-1','1.2','1e2','9223372036854775808','"1"','null','true','01','+1']) {
  assert.throws(() => api.parseJson(`{"id":${input}}`), SyntaxError);
}
for (const input of ['', '[1,]', '{"x":}', '{"x" 1}', '{"x":1,}', 'true false', '[01]',
  '{"x":"bad\\q"}', '{"x":"line\nraw"}', 'undefined', '[1e]', '[.1]', '{', '[[']) {
  assert.throws(() => api.parseJson(input), SyntaxError, input);
}
const ordinary = '{"x":[1,-2,1.5,1e2,true,false,null,"\\\" \\u00e7 😀"],"instrutor_id":null,"__proto__":{"safe":true}}';
assert.deepEqual(api.parseJson(ordinary), JSON.parse(ordinary));
assert.equal(Object.getPrototypeOf(api.parseJson(ordinary)), Object.prototype);
assert.equal({}.safe, undefined);
assert.deepEqual(api.parseJson('{"\\u0069d":9007199254740993}'), {id:'9007199254740993'});
assert.equal(api.parseJson('{"text":"id:9223372036854775807"}').text, 'id:9223372036854775807');
for (const value of [1, 9007199254740992, '01', '0', '-1', '1e3', '', '9223372036854775808']) {
  assert.equal(api.parseId(value), null);
  assert.throws(() => api.serializeBody({usuario_id:value}), error => error.status === 400);
}
for (const failure of [new TypeError('private'), new DOMException('private','AbortError'), new DOMException('private','TimeoutError')]) {
  globalThis.fetch = async () => { throw failure; };
  await assert.rejects(api.getJson('/api/alunos'), error => error.status === 0);
  globalThis.fetch = async () => new Response(new ReadableStream({ start(controller) { controller.error(failure); } }));
  await assert.rejects(api.getJson('/api/alunos'), error => error.status === 0);
}
for (const status of [400,401,403,404,409,500]) {
  globalThis.fetch = async () => response('private SQL',status);
  await assert.rejects(api.getJson('/api/alunos'), error => error.status === status && error.message === 'Request failed');
}
globalThis.fetch = async () => response('{bad');
await assert.rejects(api.getJson('/api/alunos'), error => error.status === 502);

class Element {
  constructor(tag, attrs = {}) {
    this.tagName = tag; this.attributes = {...attrs}; this.children = []; this.listeners = {};
    this.id = attrs.id || ''; this.value = attrs.value || ''; this.defaultValue = this.value;
    this.disabled = 'disabled' in attrs; this.hidden = 'hidden' in attrs;
    this.required = 'required' in attrs; this.type = attrs.type; this.dataset = {};
    for (const [key,value] of Object.entries(attrs)) if (key.startsWith('data-')) this.dataset[key.slice(5)] = value;
    this.classList = { toggle(){}, add(){}, remove(){}, contains(){return false;} };
    this.isConnected = true;
  }
  append(...children) {
    for (const child of children) {
      if (child.tagName === 'fragment') this.append(...child.children);
      else { this.children.push(child); if (typeof child !== 'string') child.parent = this; }
    }
  }
  replaceChildren(...children) { for(const child of this.children) if(typeof child !== 'string') child.isConnected=false; this.children=[]; this.append(...children); }
  set textContent(value) { this.replaceChildren(String(value)); }
  get textContent() { return this.children.map(child => typeof child === 'string' ? child : child.textContent).join(''); }
  set innerHTML(value) { throw new Error('Unsafe HTML sink'); }
  addEventListener(type, callback, options) { (this.listeners[type] ||= []).push({callback, once: options?.once}); }
  async fire(type) {
    const event = {currentTarget:this, target:this, prevented:false, preventDefault(){this.prevented=true;}};
    for (const handler of [...(this.listeners[type] || [])]) {
      if (handler.once) this.listeners[type] = this.listeners[type].filter(item => item !== handler);
      await handler.callback(event);
    }
    return event;
  }
  setAttribute(key,value) { this.attributes[key]=value; }
  getAttribute(key) { return this.attributes[key]; }
  removeAttribute(key) { delete this.attributes[key]; }
  focus() { document.activeElement=this; }
  querySelectorAll(selector) {
    const matches = [];
    for (const child of this.children) if (typeof child !== 'string') {
      if (selector.split(',').map(s=>s.trim()).includes(child.tagName)) matches.push(child);
      matches.push(...child.querySelectorAll(selector));
    }
    return matches;
  }
  setCustomValidity(value) { this.validation=value; }
  get validity() { return {valid:this.disabled || (!this.validation && (!this.required || !!this.value)
    && (this.type !== 'email' || /^[^@]+@[^@]+$/.test(this.value)))}; }
  reportValidity() { return this.querySelectorAll('input, select').every(input => input.validity.valid); }
  reset() { for (const input of this.querySelectorAll('input, select')) input.value=input.defaultValue; }
}
let root;
function fixture() {
  function build(node) {
    if (typeof node === 'string') return node;
    const element = new Element(node.tag,node.attrs);
    element.append(...node.children.map(build));
    if (node.tag === 'select') { element.value=element.children.find(child=>child.tagName==='option')?.value || ''; element.defaultValue=element.value; }
    return element;
  }
  root=build(markup);
  const all = () => { const result=[]; function walk(node){ if(typeof node==='string')return; result.push(node); node.children.forEach(walk); } walk(root); return result; };
  globalThis.document = {
    getElementById(id){return all().find(element=>element.id===id) || null;},
    createElement(tag){return new Element(tag);}, createDocumentFragment(){return new Element('fragment');},
    querySelectorAll(){return [];},
  };
  const instances = new Map();
  class Modal {
    static getInstance(element){return instances.get(element);}
    static getOrCreateInstance(element){if(!instances.has(element))instances.set(element,new Modal(element));return instances.get(element);}
    constructor(element){this.element=element;}
    show(){this.element.hidden=false; return this.element.fire('shown.bs.modal');}
    async hide(){const event=await this.element.fire('hide.bs.modal'); if(!event.prevented){this.element.hidden=true; await this.element.fire('hidden.bs.modal');}}
  }
  globalThis.window = {bootstrap:{Modal,Offcanvas:{getInstance(){return null;}}},addEventListener(){}};
  globalThis.location = {hash:'#alunos',destinations:[],replace(path){this.destinations.push(path);}};
  return document.getElementById;
}
const academy='9007199254740993', profileId='9223372036854775807';
const actor={userId:'100',academiaId:academy,perfilId:'90'};
const userRaw = (id='201', name='Aluno real', active=true, perfil=profileId) =>
  `{"id":${id},"academia_id":${academy},"perfil_id":${perfil},"nome":${JSON.stringify(name)},"email":"aluno@example.test","ativo":${active},"criado_em":"2026-11-16 12:34:56"}`;
const alunoRaw = (id='301', user='201') => `{"id":${id},"usuario_id":${user},"criado_em":"2026-11-16 12:34:56"}`;
let e, module, calls, mode, recordBodies, listRaw, usersRaw, profileRaw, writeStatus;
let sequence=0;
async function setup() {
  e=fixture(); calls=[]; mode='normal'; recordBodies=[]; writeStatus=200;
  listRaw=`[${alunoRaw()}]`; usersRaw=`[${userRaw()},${userRaw('202','Inativo',false)},${userRaw('203','Elegível')},${userRaw('204','Instrutor',true,'91')}]`;
  profileRaw=`[{"id":${profileId},"nome":"Aluno","ativo":1}]`;
  globalThis.fetch=async (url,options={}) => {
    calls.push({url,...options});
    if(options.method==='POST'||options.method==='PUT') {
      recordBodies.push(options.body);
      if(mode==='transport') throw new TypeError('private transport');
      if(mode==='invalid-write') return response('invalid');
      if(writeStatus!==200)return response('{"erro":"private SQL"}',writeStatus);
      if(url==='/api/usuarios')return response(userRaw('9223372036854775806','Nova conta'),201);
      if(url==='/api/alunos')return response(alunoRaw('302',api.parseJson(options.body).usuario_id),201);
      if(url.endsWith('/status'))return response(userRaw(url.split('/')[3],'Alterado',JSON.parse(options.body).ativo));
      return response(userRaw(url.split('/')[3],JSON.parse(options.body).nome));
    }
    if(url==='/api/perfis') {
      if(mode==='profile-error')return response('SQL',500);
      return response(profileRaw);
    }
    if(mode==='get-transport')throw new TypeError('SQL');
    if(mode==='get-invalid')return response('{}');
    if(typeof mode==='number')return response('SQL',mode);
    return response(url==='/api/alunos'?listRaw:usersRaw);
  };
  const text=(await readFile('public/js/alunos.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL));
  module=await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64')+'#'+sequence++);
  module.initAlunos(actor);
  await module.visitAlunos();
}
const rowButtons=()=>e('alunos-rows').querySelectorAll('button');
async function newAccount() {
  await e('create-aluno').fire('click');
  e('aluno-create-name').value='Nova conta';
  e('aluno-create-email').value='nova@example.test';
  e('aluno-create-password').value=' secret " senha ';
}
await setup();
assert.equal(e('alunos').tagName,'section');
assert.equal(e('aluno-create-password').type,'password');
assert.equal(e('aluno-create-password').getAttribute('autocomplete'),'new-password');
assert.equal(root.querySelectorAll('a').some(link=>link.getAttribute('href')==='#alunos'&&link.dataset.page==='alunos'),true);
for(const id of ['aluno-create-name','aluno-create-email','aluno-create-password','aluno-edit-name','aluno-edit-email','aluno-create-mode','aluno-existing-user']) {
  assert(root.querySelectorAll('label').some(label=>label.getAttribute('for')===id));
}
for(const name of ['create','edit','status']) {
  assert.equal(e(`aluno-${name}-modal`).getAttribute('aria-labelledby'),`aluno-${name}-title`);
  assert.equal(e(`aluno-${name}-feedback`).getAttribute('aria-live'),'polite');
}
assert.equal(e('alunos-table-container').getAttribute('role'),'region');
assert.equal(e('alunos-table-container').getAttribute('tabindex'),'0');
assert.equal(e('alunos-rows').parent.querySelectorAll('th').every(th=>th.getAttribute('scope')==='col'),true);
assert.equal(calls.filter(call=>call.url==='/api/alunos').length,1);
assert.equal(calls.filter(call=>call.url===`/api/usuarios?academia_id=${academy}`).length,1);
assert.equal(calls.some(call=>/^\/api\/usuarios\//.test(call.url)),false);
assert.match(e('alunos-rows').textContent,/Aluno real/);
assert.match(e('alunos-rows').textContent,/aluno@example.test/);
assert.match(e('alunos-rows').textContent,/16\/11\/2026 12:34/);
assert.equal(e('alunos-rows').children.length,1);
assert.equal(e('aluno-existing-user').children.length,2); // placeholder and only eligible account
for (const [input,expected] of [['2024-02-29 23:59:59','29/02/2024 23:59'],['2023-02-29 12:00:00','Data indisponível'],['2026-13-01 00:00:00','Data indisponível'],['2026-01-01 24:00:00','Data indisponível'],['bad','Data indisponível']]) assert.equal(module.formatAlunoDate(input),expected);
listRaw=`[${alunoRaw()},${alunoRaw('302','202')},${alunoRaw('303','999')}]`;
await module.loadAlunos();
assert.equal(e('alunos-rows').children.length,3);
assert.match(e('alunos-rows').textContent,/Inativo/);
assert.match(e('alunos-rows').textContent,/Dados do usuário indisponíveis/);
assert.equal(rowButtons().at(-1).disabled,true);
assert.equal(rowButtons().at(-2).disabled,true);
listRaw=`[${alunoRaw('304','100')}]`;usersRaw=`[${userRaw('100','Própria conta')}]`;
await module.loadAlunos();assert.equal(rowButtons()[1].disabled,true);
assert.match(e('alunos-rows').textContent,/Você não pode desativar/);
await setup(); mode='profile-error'; await module.loadAlunos();
assert.equal(e('alunos-rows').children.length,1);assert.equal(e('create-aluno').disabled,true);
for(const raw of ['[]',`[{"id":${profileId},"nome":"Aluno","ativo":0}]`]) {
  mode='normal';profileRaw=raw;await module.loadAlunos();assert.equal(e('create-aluno').disabled,true);
}
await setup();listRaw='[]';await module.loadAlunos();assert.match(e('alunos-state').textContent,/Nenhum aluno cadastrado/);
assert.equal(e('alunos-empty-create').disabled,false);
for (const status of [403,404,500,'get-transport','get-invalid']) {
  await setup();mode=status;await module.loadAlunos();
  assert.equal(e('alunos-error').hidden,false);assert.equal(e('alunos-error-message').textContent.includes('SQL'),false);
  assert.deepEqual(location.destinations,[]);
  mode='normal';await e('retry-alunos').fire('click');assert.equal(e('alunos-table-container').hidden,false);
  assert.equal(calls.some(call=>call.method!=='GET'),false);
}
await setup();mode=401;await module.loadAlunos();assert(location.destinations.includes('/login.html'));
assert.equal(e('authenticated-app').hidden,true);
await setup();
let release;const originalFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>url==='/api/alunos'?new Promise(resolve=>{release=()=>resolve(response(listRaw));}):originalFetch(url,options);
const load=module.loadAlunos();await module.loadAlunos();
assert.equal(e('refresh-alunos').disabled,true);assert.equal(e('alunos-panel').getAttribute('aria-busy'),'true');
assert.match(e('alunos-state').textContent,/Carregando alunos/);release();await load;

await setup();let releaseAccounts;let reads=0;const metadataFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>{
  if(url==='/api/alunos'){reads++;return Promise.resolve(response('SQL',500));}
  if(url.startsWith('/api/usuarios?')){reads++;return new Promise(resolve=>{releaseAccounts=()=>resolve(response(usersRaw));});}
  return metadataFetch(url,options);
};
const failedLoad=module.loadAlunos();await new Promise(resolve=>setImmediate(resolve));
await module.loadAlunos();assert.equal(reads,2);assert.equal(e('refresh-alunos').disabled,true);
releaseAccounts();await failedLoad;assert.equal(e('alunos-error').hidden,false);

await setup();await newAccount();await e('aluno-create-form').fire('submit');
assert.equal(calls.filter(call=>call.url==='/api/usuarios').length,1);
assert.equal(calls.filter(call=>call.method==='POST'&&call.url==='/api/alunos').length,1);
assert.equal(recordBodies[0],`{"academia_id":${academy},"perfil_id":${profileId},"nome":"Nova conta","email":"nova@example.test","senha":${JSON.stringify(' secret " senha ')}}`);
assert.equal(recordBodies[1],'{"usuario_id":9223372036854775806}');
assert.equal(e('aluno-create-password').value,'');assert.match(e('alunos-feedback').textContent,/sucesso/);
assert.equal(e('alunos-rows').children.length,2);

await setup();await newAccount();
const initialFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>url==='/api/alunos'&&options.method==='POST'?response('SQL',500):initialFetch(url,options);
await e('aluno-create-form').fire('submit');
assert.equal(e('aluno-complete').hidden,false);assert.equal(e('aluno-create-submit').hidden,true);
assert.equal(e('aluno-create-password').value,'');
usersRaw=`[${userRaw()},${userRaw('9223372036854775806','Nova conta')}]`;
globalThis.fetch=initialFetch;
await e('aluno-complete').fire('click');
assert.equal(calls.filter(call=>call.url==='/api/usuarios').length,1);
assert.equal(e('aluno-complete').hidden,true);

await setup();await newAccount();mode='transport';await e('aluno-create-form').fire('submit');
assert.match(e('aluno-create-feedback').textContent,/não pôde ser confirmado/);
assert.equal(e('aluno-create-submit').hidden,true);
const writes=calls.filter(call=>call.method==='POST').length;
await e('aluno-create-form').fire('submit');assert.equal(calls.filter(call=>call.method==='POST').length,writes);
mode='normal';await e('aluno-reconcile').fire('click');
assert.equal(e('aluno-create-mode').value,'existing');assert.equal(e('aluno-existing-user').value,'');

await setup();await e('create-aluno').fire('click');e('aluno-create-mode').value='existing';await e('aluno-create-mode').fire('change');
e('aluno-existing-user').value='203';await e('aluno-create-form').fire('submit');
assert.deepEqual(recordBodies,['{"usuario_id":203}']);

async function regressionI1() {
  await setup();
  await e('create-aluno').fire('click');
  e('aluno-create-mode').value='existing';await e('aluno-create-mode').fire('change');
  e('aluno-existing-user').value='203';await e('aluno-existing-user').fire('change');
  writeStatus=400;
  await e('aluno-create-form').fire('submit');
  usersRaw=`[${userRaw()},${userRaw('203','Conta A',false)},${userRaw('205','Conta B')}]`;
  writeStatus=200;
  await e('aluno-complete').fire('click');
  assert.match(e('aluno-create-feedback').textContent,/não está mais elegível/);
  assert.equal(e('aluno-create-mode').disabled,true);
  assert(e('aluno-end-attempt'), 'I1: an ineligible pending registration needs an explicit exit');
  assert.equal(e('aluno-end-attempt').hidden,false);
  await window.bootstrap.Modal.getInstance(e('aluno-create-modal')).hide();
  await e('create-aluno').fire('click');
  assert.equal(e('aluno-end-attempt').hidden,false);
  const beforeEnding=calls.length;
  await e('aluno-end-attempt').fire('click');
  assert.equal(calls.length,beforeEnding,'Ending a pending attempt must not issue any request');
  assert.equal(e('aluno-create-mode').disabled,false);
  assert.equal(e('aluno-create-mode').value,'new');
  assert.equal(e('aluno-new-fields').hidden,false);
  assert.equal(e('aluno-create-submit').hidden,false);
  assert.equal(e('aluno-complete').hidden,true);
  assert.equal(e('aluno-end-attempt').hidden,true);
  assert.equal(e('aluno-create-password').value,'');
  assert.equal(e('aluno-existing-user').value,'');
  assert.equal(e('aluno-create-feedback').textContent.includes('não está mais elegível'),false);
  assert.deepEqual(e('aluno-existing-user').children.map(option=>option.value),['','205']);
  e('aluno-create-mode').value='existing';await e('aluno-create-mode').fire('change');
  e('aluno-existing-user').value='205';await e('aluno-existing-user').fire('change');
  assert.equal(e('aluno-create-submit').disabled,false);
  await e('aluno-create-form').fire('submit');
  assert.deepEqual(recordBodies,['{"usuario_id":203}','{"usuario_id":205}']);
  assert.equal(calls.filter(call=>call.method==='POST'&&call.url==='/api/usuarios').length,0);
  assert.equal(calls.some(call=>call.method==='PUT'||call.method==='DELETE'),false);
  assert.match(e('alunos-feedback').textContent,/sucesso/);

  // Recovery must remain reachable when subsequent metadata/list reads fail.
  // Ending the local attempt must not clear uncertainty about a previous write.
  await setup();await newAccount();
  const original=globalThis.fetch;
  globalThis.fetch=(url,options)=>url==='/api/alunos'&&options.method==='POST'
    ? Promise.resolve(response('SQL',500)) : original(url,options);
  await e('aluno-create-form').fire('submit');
  await window.bootstrap.Modal.getInstance(e('aluno-create-modal')).hide();
  mode='profile-error';await module.loadAlunos();
  assert.equal(e('create-aluno').disabled,false);
  await e('create-aluno').fire('click');
  assert.equal(e('aluno-end-attempt').hidden,false);
  assert.equal(document.activeElement.id,'aluno-end-attempt');
  await window.bootstrap.Modal.getInstance(e('aluno-create-modal')).hide();
  mode=500;await module.loadAlunos();
  await e('create-aluno').fire('click');
  assert.equal(e('aluno-create-modal').hidden,false);
  assert.equal(e('aluno-end-attempt').hidden,false);
  const beforeCancel=calls.length;
  await e('aluno-end-attempt').fire('click');
  assert.equal(calls.length,beforeCancel);
  assert.equal(e('aluno-create-password').value,'');
  assert.equal(e('aluno-create-mode').disabled,false);
  mode='normal';await module.loadAlunos();
  assert.equal(e('aluno-create-submit').disabled,false);
}

async function regressionI2() {
  await setup();
  await e('create-aluno').fire('click');
  e('aluno-create-mode').value='existing';await e('aluno-create-mode').fire('change');
  e('aluno-existing-user').value='203';await e('aluno-existing-user').fire('change');
  e('aluno-create-mode').value='new';await e('aluno-create-mode').fire('change');
  assert.equal(e('aluno-existing-user').value,'');
  await newAccount();mode='transport';
  await e('aluno-create-form').fire('submit');
  assert.equal(e('aluno-create-password').value,'');
  usersRaw=`[${userRaw()},${userRaw('203','Conta A')},${userRaw('205','Conta B')},${userRaw('206','Outra conta')}]`;
  mode='normal';await e('aluno-reconcile').fire('click');
  assert.equal(e('aluno-create-mode').value,'existing');
  assert.equal(e('aluno-existing-user').value,'','I2: reconciliation must discard a previous unrelated selection');
  assert.equal(e('aluno-create-submit').disabled,true);
  assert.equal(e('aluno-create-password').value,'');
  assert.equal(calls.filter(call=>call.url==='/api/alunos'&&call.method==='POST').length,0);
  await e('aluno-create-form').fire('submit');
  assert.equal(calls.filter(call=>call.url==='/api/alunos'&&call.method==='POST').length,0);
  await window.bootstrap.Modal.getInstance(e('aluno-create-modal')).hide();
  await e('create-aluno').fire('click');
  assert.equal(e('aluno-existing-user').value,'');
  assert.equal(e('aluno-create-submit').disabled,true);
  e('aluno-existing-user').value='205';await e('aluno-existing-user').fire('change');
  assert.equal(e('aluno-create-submit').disabled,false);
  await e('aluno-create-form').fire('submit');
  assert.deepEqual(recordBodies.slice(1),['{"usuario_id":205}']);
  assert.equal(calls.filter(call=>call.url==='/api/usuarios'&&call.method==='POST').length,1);
  assert.match(e('alunos-feedback').textContent,/sucesso/);
}

await regressionI1();
await regressionI2();

// A timed-out Aluno write may already exist. Reconciliation must finish without
// another POST, including after a concurrent request returns 409.
for(const failure of ['transport',409]) {
  await setup();await e('create-aluno').fire('click');
  e('aluno-create-mode').value='existing';await e('aluno-create-mode').fire('change');
  e('aluno-existing-user').value='203';
  if(failure==='transport')mode='transport';else writeStatus=failure;
  await e('aluno-create-form').fire('submit');
  assert.equal(e('aluno-complete').hidden,false);
  const postCount=calls.filter(call=>call.method==='POST').length;
  listRaw=`[${alunoRaw()},${alunoRaw('302','203')}]`;mode='normal';writeStatus=200;
  await e('aluno-complete').fire('click');
  assert.equal(calls.filter(call=>call.method==='POST').length,postCount);
  assert.match(e('alunos-feedback').textContent,/sucesso/);
}

for(const status of [400,403,404,409,500]) {
  await setup();await newAccount();writeStatus=status;
  await e('aluno-create-form').fire('submit');
  assert.equal(e('aluno-create-password').value,'');
  assert.equal(calls.filter(call=>call.url==='/api/alunos'&&call.method==='POST').length,0);
  assert.equal(e('aluno-create-feedback').textContent.includes('SQL'),false);
}

for(const id of limits) {
  await setup();listRaw=`[${alunoRaw(id,id)}]`;usersRaw=`[${userRaw(id)}]`;await module.loadAlunos();
  await rowButtons()[0].fire('click');assert.equal(e('aluno-edit-name').value,'Aluno real');
  e('aluno-edit-name').value='Nome alterado';await e('aluno-edit-form').fire('submit');
  assert.equal(calls.at(-1).url,`/api/usuarios/${id}`);
  assert.equal(recordBodies.at(-1),'{"nome":"Nome alterado","email":"aluno@example.test"}');
  assert.match(e('alunos-rows').textContent,/Nome alterado/);
  await rowButtons()[1].fire('click');await e('aluno-status-submit').fire('click');
  assert.equal(calls.at(-1).url,`/api/usuarios/${id}/status`);assert.equal(recordBodies.at(-1),'{"ativo":false}');
  assert.match(e('alunos-rows').textContent,/Inativo/);assert.equal(rowButtons()[1].textContent,'Ativar');
  await rowButtons()[1].fire('click');await e('aluno-status-submit').fire('click');
  assert.equal(recordBodies.at(-1),'{"ativo":true}');assert.equal(e('alunos-rows').children.length,1);
}
for(const operation of ['edit','status']) for(const status of [400,403,404,409,500,'transport']) {
  await setup();await rowButtons()[operation==='edit'?0:1].fire('click');
  if(status==='transport')mode='transport';else writeStatus=status;
  await e(operation==='edit'?'aluno-edit-form':'aluno-status-submit').fire(operation==='edit'?'submit':'click');
  assert.equal(e('alunos-rows').textContent.includes('Aluno real'),true);
  assert.equal(e(`aluno-${operation}-feedback`).textContent.includes('SQL'),false);
  const count=calls.filter(call=>call.method==='PUT').length;
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.filter(call=>call.method==='PUT').length,count);
}
// Hold each PUT to prove no optimistic status, duplicate writes or refresh can
// race with an operation. The response alone updates the final row.
for(const operation of ['edit','status']) {
  await setup();await rowButtons()[operation==='edit'?0:1].fire('click');
  const underlyingPut=globalThis.fetch;let releasePut;let puts=0;
  globalThis.fetch=(url,options)=>options.method==='PUT'?new Promise(resolve=>{
    puts++;releasePut=async()=>resolve(await underlyingPut(url,options));
  }):underlyingPut(url,options);
  const target=e(operation==='edit'?'aluno-edit-form':'aluno-status-submit');
  const event=operation==='edit'?'submit':'click';
  const inFlight=target.fire(event);await target.fire(event);await module.loadAlunos();
  assert.equal(puts,1);assert.equal(e('refresh-alunos').disabled,true);
  assert.equal(e('alunos-rows').textContent.includes('Inativo'),false);
  await releasePut();await inFlight;
  assert.equal(e('refresh-alunos').disabled,false);
}
await setup();await newAccount();let resolvePost;
const underlying=globalThis.fetch;
globalThis.fetch=(url,options)=>url==='/api/usuarios'?new Promise(resolve=>{resolvePost=()=>resolve(response(userRaw('205'),201));}):underlying(url,options);
const submit=e('aluno-create-form').fire('submit');await e('aluno-create-form').fire('submit');
assert.equal(e('aluno-create-submit').disabled,true);assert.equal(e('aluno-create-password').value,'');
assert.equal((await e('aluno-create-modal').fire('hide.bs.modal')).prevented,true);
resolvePost();await submit;

await setup();
const attack='<script>alert(1)</script><img src=x onerror=alert(1)> " \' & < >';
usersRaw=`[${userRaw('201',attack)}]`;await module.loadAlunos();
assert(e('alunos-rows').textContent.includes(attack));assert.equal(e('alunos-rows').querySelectorAll('script, img').length,0);
await rowButtons()[1].fire('click');assert(e('aluno-status-question').textContent.includes(attack));
assert.equal(e('aluno-status-question').querySelectorAll('script, img').length,0);
usersRaw=`[${userRaw('201',attack).replace('"aluno@example.test"',JSON.stringify(attack))}]`;
await module.loadAlunos();assert(e('alunos-rows').children[0].children[1].textContent.includes(attack));
assert.equal(e('alunos-rows').querySelectorAll('script, img').length,0);

// Academias consumes the same ID representation; render a maximum-width ID
// through the real module rather than only checking its source.
fixture();
globalThis.fetch=async()=>response('[{"id":9223372036854775807,"nome":"Academia lossless","ativo":true,"cnpj":null,"email":null,"telefone":null}]');
const academiaSource=(await readFile('public/js/academias.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL));
const academias=await import('data:text/javascript;base64,'+Buffer.from(academiaSource).toString('base64'));
await academias.loadAcademias();
assert(document.getElementById('academias-rows').textContent.includes('9223372036854775807'));
assert(document.getElementById('academias-rows').textContent.includes('Academia lossless'));

// Deliver the real app import graph for direct-hash/session ordering checks.
for(const status of [200,401,403]) {
  fixture();const order=[];let releaseAuth;
  globalThis.fetch=async(url,options)=>{
    order.push(url);
    if(url==='/api/auth/me')return new Promise(resolve=>{releaseAuth=()=>resolve(response(status===200?'{"userId":100,"academiaId":9007199254740993,"perfilId":90}':'{}',status));});
    if(url==='/api/alunos')return response('[]');
    if(url.startsWith('/api/usuarios'))return response('[]');
    if(url==='/api/perfis')return response(profileRaw);
    return response('{}');
  };
  let alunoSource=(await readFile('public/js/alunos.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL));
  const alunoURL='data:text/javascript;base64,'+Buffer.from(alunoSource+'\n// '+sequence++).toString('base64');
  let appSource=(await readFile('public/js/app.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL))
    .replace("'./alunos.js'",JSON.stringify(alunoURL))
    .replace("'./academias.js'",JSON.stringify('data:text/javascript,export function loadAcademias(){}'));
  await import('data:text/javascript;base64,'+Buffer.from(appSource+'\n// '+sequence++).toString('base64'));
  assert.deepEqual(order,['/api/auth/me']);releaseAuth();
  for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(order.includes('/api/alunos'),status===200);
  assert.equal(document.title,'Alunos | TrainingHub');
  if(status===401)assert.deepEqual(location.destinations,['/login.html']);
  if(status===403)assert.deepEqual(location.destinations,[]);
}
console.log(JSON.stringify({checks,bodies}));
'''


def check_javascript():
    node = shutil.which("node")
    if not node:
        candidate = Path("C:/Program Files/nodejs/node.exe")
        node = str(candidate) if candidate.exists() else None
    if not node:
        raise RuntimeError("TH-31 critical int64/JavaScript checks NOT EXECUTED: install Node; this suite cannot pass without them.")
    markup = Markup()
    markup.feed((ROOT / "public/index.html").read_text(encoding="utf-8"))
    script = JS.replace("__MARKUP__", json.dumps(markup.root, ensure_ascii=True))
    result = subprocess.check_output([node, "--input-type=module", "-"], input=script,
                                     text=True, encoding="utf-8", cwd=ROOT)
    report = json.loads(result)
    print(f"TH-31 JavaScript/DOM: {report['checks']} assertions passed; int64/parser/serializer, list/join, states, registration/recovery, edit/status, XSS, auth ordering. Not visual proof.", flush=True)
    return report["bodies"]


def check_http(bodies):
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                       "--fixture-hash"], env=env, text=True).strip()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="th31-", dir=ROOT / "build") as temporary:
        directory = Path(temporary)
        database = directory / "alunos.db"
        with closing(sqlite3.connect(database)) as db:
            for migration in sorted((ROOT / "migrations").glob("*.sql")):
                db.executescript(migration.read_text(encoding="utf-8"))
            db.execute("INSERT INTO academia(id,nome) VALUES(1,'Tenant de teste')")
            insert_admin(db, encoded)
            profile = db.execute("SELECT id FROM perfil WHERE nome='Aluno'").fetchone()[0]
            for identity in [1, 2**40, 9007199254740993]:
                db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) VALUES(?,1,?,'Aluno',?,?)",
                           (identity, profile, f"u{identity}@example.test", encoded))
            db.commit()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        config["listeners"] = [{"address": "127.0.0.1", "port": port}]
        config["db_clients"][0]["filename"] = database.as_posix()
        config["app"]["document_root"] = (ROOT / "public").as_posix()
        (directory / "config.json").write_text(json.dumps(config), encoding="utf-8")
        base = f"http://127.0.0.1:{port}"
        with (directory / "server.log").open("w", encoding="utf-8") as log:
            server = subprocess.Popen([str(ROOT / "build/traininghub.exe")], cwd=directory,
                                      env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(base + "/api/health", timeout=1):
                            break
                    except OSError:
                        if server.poll() is not None:
                            raise RuntimeError("TH-31 isolated server exited before readiness")
                        time.sleep(.1)
                else:
                    raise RuntimeError("TH-31 isolated server unavailable")
                client = login_client(base)

                def request(method, path, body=None, status=200):
                    nonlocal checked
                    data = body.encode() if isinstance(body, str) else json.dumps(body).encode() if body is not None else None
                    req = urllib.request.Request(base + path, method=method, data=data,
                                                 headers={"Content-Type": "application/json"})
                    try:
                        result = client.open(req, timeout=15)
                    except urllib.error.HTTPError as error:
                        result = error
                    with result:
                        content = result.read()
                        assert result.code == status, (path, result.code)
                        if method == "PUT":
                            assert result.headers.get("Cache-Control") == "no-store"
                        assert b"senha_hash" not in content
                        checked += 1
                        return json.loads(content)

                new_account = request("POST", "/api/usuarios", {"academia_id": 1, "perfil_id": profile,
                    "nome": "Conta criada pela interface", "email": "nova.th31@example.test",
                    "senha": "TH31-test-password"}, 201)
                request("POST", "/api/alunos", {"usuario_id": new_account["id"]}, 201)
                # Seed INT64_MAX only after POST Usuario: SQLite AUTOINCREMENT
                # cannot create another account once that maximum row exists.
                with closing(sqlite3.connect(database)) as db:
                    db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) VALUES(?,1,?,'Limite',?,?)",
                               (2**63-1, profile, "max@example.test", encoded))
                    db.commit()
                for body in bodies:
                    identity = json.loads(body)["usuario_id"]
                    aluno = request("POST", "/api/alunos", body, 201)
                    assert aluno["usuario_id"] == identity
                    assert request("GET", f"/api/alunos/{aluno['id']}") == aluno
                    updated = request("PUT", f"/api/usuarios/{identity}", {"nome": "Editado", "email": f"edit{identity}@example.test"})
                    assert updated["id"] == identity
                    assert request("PUT", f"/api/usuarios/{identity}/status", {"ativo": False})["ativo"] is False
                    assert request("PUT", f"/api/usuarios/{identity}/status", {"ativo": True})["ativo"] is True
                assert len(request("GET", "/api/alunos")) == 5
                assert len(request("GET", "/api/usuarios?academia_id=1")) == 6
                assert any(item["nome"] == "Aluno" for item in request("GET", "/api/perfis"))
                with urllib.request.urlopen(base + "/js/alunos.js") as result:
                    assert result.code == 200 and result.read()
                    checked += 1
            finally:
                server.terminate()
                server.wait(timeout=10)
    print(f"TH-31 real HTTP: {checked} requests passed with temporary SQLite; exact JS-generated int64 bodies accepted.", flush=True)


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).hexdigest() if development.exists() else None
    try:
        check_http(check_javascript())
    finally:
        after = hashlib.sha256(development.read_bytes()).hexdigest() if development.exists() else None
        assert before == after, "Development database changed"
    print("TH-31 development database unchanged.")


if __name__ == "__main__":
    run()
