"""TH-32: delivered JavaScript/DOM behavior and isolated real HTTP contracts.

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
  await api.postJson('/api/instrutores',{usuario_id:id});assert.equal(sent.at(-1).body,`{"usuario_id":${id}}`);
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
  await assert.rejects(api.getJson('/api/instrutores'), error => error.status === 0);
  globalThis.fetch = async () => new Response(new ReadableStream({ start(controller) { controller.error(failure); } }));
  await assert.rejects(api.getJson('/api/instrutores'), error => error.status === 0);
}
for (const status of [400,401,403,404,409,500]) {
  globalThis.fetch = async () => response('private SQL',status);
  await assert.rejects(api.getJson('/api/instrutores'), error => error.status === status && error.message === 'Request failed');
}
globalThis.fetch = async () => response('{bad');
await assert.rejects(api.getJson('/api/instrutores'), error => error.status === 502);

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
  globalThis.location = {hash:'#instrutores',destinations:[],replace(path){this.destinations.push(path);}};
  return document.getElementById;
}
const academy='9007199254740993', profileId='9223372036854775807';
const actor={userId:'100',academiaId:academy,perfilId:'90'};
const userRaw = (id='201', name='Instrutor real', active=true, perfil=profileId) =>
  `{"id":${id},"academia_id":${academy},"perfil_id":${perfil},"nome":${JSON.stringify(name)},"email":"instrutor@example.test","ativo":${active},"criado_em":"2026-11-16 12:34:56"}`;
const instrutorRaw = (id='301', user='201') => `{"id":${id},"usuario_id":${user},"criado_em":"2026-11-16 12:34:56"}`;
let e, module, calls, mode, recordBodies, listRaw, usersRaw, profileRaw, writeStatus;
let sequence=0;
async function setup() {
  e=fixture(); calls=[]; mode='normal'; recordBodies=[]; writeStatus=200;
  listRaw=`[${instrutorRaw()}]`; usersRaw=`[${userRaw()},${userRaw('202','Inativo',false)},${userRaw('203','Elegível')},${userRaw('204','Aluno',true,'91')}]`;
  profileRaw=`[{"id":${profileId},"nome":"Instrutor","ativo":1}]`;
  globalThis.fetch=async (url,options={}) => {
    calls.push({url,...options});
    if(options.method==='POST'||options.method==='PUT') {
      recordBodies.push(options.body);
      if(mode==='transport') throw new TypeError('private transport');
      if(mode==='invalid-write') return response('invalid');
      if(writeStatus!==200)return response('{"erro":"private SQL"}',writeStatus);
      if(url==='/api/usuarios')return response(userRaw('9223372036854775806','Nova conta'),201);
      if(url==='/api/instrutores')return response(instrutorRaw('302',api.parseJson(options.body).usuario_id),201);
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
    return response(url==='/api/instrutores'?listRaw:usersRaw);
  };
  const text=(await readFile('public/js/instrutores.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL));
  module=await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64')+'#'+sequence++);
  module.initInstrutores(actor);
  await module.visitInstrutores();
}
const rowButtons=()=>e('instrutores-rows').querySelectorAll('button');
async function newAccount() {
  await e('create-instrutor').fire('click');
  e('instrutor-create-name').value='Nova conta';
  e('instrutor-create-email').value='nova@example.test';
  e('instrutor-create-password').value=' secret " senha ';
}

// M1: abandoning new-account mode discards the password without any request.
{
  await setup();await newAccount();
  assert.equal(e('instrutor-create-mode').value,'new');
  assert.notEqual(e('instrutor-create-password').value,'');
  const before=calls.length;
  e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(e('instrutor-new-fields').hidden,true);
  assert.equal(e('instrutor-create-password').disabled,true);
  assert.equal(e('instrutor-create-name').value,'Nova conta');
  assert.equal(e('instrutor-create-email').value,'nova@example.test');
  assert.equal(calls.length,before);
  e('instrutor-existing-user').value='203';await e('instrutor-existing-user').fire('change');
  e('instrutor-create-mode').value='new';await e('instrutor-create-mode').fire('change');
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(e('instrutor-create-password').disabled,false);
  assert.equal(e('instrutor-existing-user').value,'');
  assert.equal(calls.length,before);
  await e('instrutor-create-form').fire('submit');
  assert.equal(calls.length,before,'A new account requires the password to be entered again');
  assert.equal(calls.filter(call=>['POST','PUT','DELETE'].includes(call.method)).length,0);
}

await setup();
assert.equal(e('instrutores').tagName,'section');
assert.equal(e('instrutor-create-password').type,'password');
assert.equal(e('instrutor-create-password').getAttribute('autocomplete'),'new-password');
assert.equal(root.querySelectorAll('a').some(link=>link.getAttribute('href')==='#instrutores'&&link.dataset.page==='instrutores'),true);
for(const id of ['instrutor-create-name','instrutor-create-email','instrutor-create-password','instrutor-edit-name','instrutor-edit-email','instrutor-create-mode','instrutor-existing-user']) {
  assert(root.querySelectorAll('label').some(label=>label.getAttribute('for')===id));
}
for(const name of ['create','edit','status']) {
  assert.equal(e(`instrutor-${name}-modal`).getAttribute('aria-labelledby'),`instrutor-${name}-title`);
  assert.equal(e(`instrutor-${name}-feedback`).getAttribute('aria-live'),'polite');
}
assert.equal(e('instrutores-table-container').getAttribute('role'),'region');
assert.equal(e('instrutores-table-container').getAttribute('tabindex'),'0');
assert.equal(e('instrutores-rows').parent.querySelectorAll('th').every(th=>th.getAttribute('scope')==='col'),true);
assert.equal(calls.filter(call=>call.url==='/api/instrutores').length,1);
assert.equal(calls.filter(call=>call.url===`/api/usuarios?academia_id=${academy}`).length,1);
assert.equal(calls.some(call=>/^\/api\/usuarios\//.test(call.url)),false);
assert.match(e('instrutores-rows').textContent,/Instrutor real/);
assert.match(e('instrutores-rows').textContent,/instrutor@example.test/);
assert.match(e('instrutores-rows').textContent,/16\/11\/2026 12:34/);
assert.equal(e('instrutores-rows').children.length,1);
assert.equal(e('instrutor-existing-user').children.length,2); // placeholder and only eligible account
for (const [input,expected] of [['2024-02-29 23:59:59','29/02/2024 23:59'],['2023-02-29 12:00:00','Data indisponível'],['2026-13-01 00:00:00','Data indisponível'],['2026-01-01 24:00:00','Data indisponível'],['bad','Data indisponível']]) assert.equal(module.formatInstrutorDate(input),expected);
listRaw=`[${instrutorRaw()},${instrutorRaw('302','202')},${instrutorRaw('303','999')}]`;
await module.loadInstrutores();
assert.equal(e('instrutores-rows').children.length,3);
assert.match(e('instrutores-rows').textContent,/Inativo/);
assert.match(e('instrutores-rows').textContent,/Dados do usuário indisponíveis/);
assert.equal(rowButtons().at(-1).disabled,true);
assert.equal(rowButtons().at(-2).disabled,true);
listRaw=`[${instrutorRaw('304','100')}]`;usersRaw=`[${userRaw('100','Própria conta')}]`;
await module.loadInstrutores();assert.equal(rowButtons()[1].disabled,true);
assert.match(e('instrutores-rows').textContent,/Você não pode desativar/);
await setup(); mode='profile-error'; await module.loadInstrutores();
assert.equal(e('instrutores-rows').children.length,1);assert.equal(e('create-instrutor').disabled,true);
for(const raw of ['[]',`[{"id":${profileId},"nome":"Instrutor","ativo":0}]`]) {
  mode='normal';profileRaw=raw;await module.loadInstrutores();assert.equal(e('create-instrutor').disabled,true);
}
await setup();listRaw='[]';await module.loadInstrutores();assert.match(e('instrutores-state').textContent,/Nenhum instrutor cadastrado/);
assert.equal(e('instrutores-empty-create').disabled,false);
for (const status of [403,404,500,'get-transport','get-invalid']) {
  await setup();mode=status;await module.loadInstrutores();
  assert.equal(e('instrutores-error').hidden,false);assert.equal(e('instrutores-error-message').textContent.includes('SQL'),false);
  assert.deepEqual(location.destinations,[]);
  mode='normal';await e('retry-instrutores').fire('click');assert.equal(e('instrutores-table-container').hidden,false);
  assert.equal(calls.some(call=>call.method!=='GET'),false);
}
await setup();mode=401;await module.loadInstrutores();assert(location.destinations.includes('/login.html'));
assert.equal(e('authenticated-app').hidden,true);
await setup();
let release;const originalFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>url==='/api/instrutores'?new Promise(resolve=>{release=()=>resolve(response(listRaw));}):originalFetch(url,options);
const load=module.loadInstrutores();await module.loadInstrutores();
assert.equal(e('refresh-instrutores').disabled,true);assert.equal(e('instrutores-panel').getAttribute('aria-busy'),'true');
assert.match(e('instrutores-state').textContent,/Carregando instrutores/);release();await load;

await setup();let releaseAccounts;let reads=0;const metadataFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>{
  if(url==='/api/instrutores'){reads++;return Promise.resolve(response('SQL',500));}
  if(url.startsWith('/api/usuarios?')){reads++;return new Promise(resolve=>{releaseAccounts=()=>resolve(response(usersRaw));});}
  return metadataFetch(url,options);
};
const failedLoad=module.loadInstrutores();await new Promise(resolve=>setImmediate(resolve));
await module.loadInstrutores();assert.equal(reads,2);assert.equal(e('refresh-instrutores').disabled,true);
releaseAccounts();await failedLoad;assert.equal(e('instrutores-error').hidden,false);

await setup();await newAccount();await e('instrutor-create-form').fire('submit');
assert.equal(calls.filter(call=>call.url==='/api/usuarios').length,1);
assert.equal(calls.filter(call=>call.method==='POST'&&call.url==='/api/instrutores').length,1);
assert.equal(recordBodies[0],`{"academia_id":${academy},"perfil_id":${profileId},"nome":"Nova conta","email":"nova@example.test","senha":${JSON.stringify(' secret " senha ')}}`);
assert.equal(recordBodies[1],'{"usuario_id":9223372036854775806}');
assert.equal(e('instrutor-create-password').value,'');assert.match(e('instrutores-feedback').textContent,/sucesso/);
assert.equal(e('instrutores-rows').children.length,2);

await setup();await newAccount();
const initialFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>url==='/api/instrutores'&&options.method==='POST'?response('SQL',500):initialFetch(url,options);
await e('instrutor-create-form').fire('submit');
assert.equal(e('instrutor-complete').hidden,false);assert.equal(e('instrutor-create-submit').hidden,true);
assert.equal(e('instrutor-create-password').value,'');
usersRaw=`[${userRaw()},${userRaw('9223372036854775806','Nova conta')}]`;
globalThis.fetch=initialFetch;
await e('instrutor-complete').fire('click');
assert.equal(calls.filter(call=>call.url==='/api/usuarios').length,1);
assert.equal(e('instrutor-complete').hidden,true);

await setup();await newAccount();mode='transport';await e('instrutor-create-form').fire('submit');
assert.match(e('instrutor-create-feedback').textContent,/não pôde ser confirmado/);
assert.equal(e('instrutor-create-submit').hidden,true);
const writes=calls.filter(call=>call.method==='POST').length;
await e('instrutor-create-form').fire('submit');assert.equal(calls.filter(call=>call.method==='POST').length,writes);
mode='normal';await e('instrutor-reconcile').fire('click');
assert.equal(e('instrutor-create-mode').value,'existing');assert.equal(e('instrutor-existing-user').value,'');

await setup();await e('create-instrutor').fire('click');e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
e('instrutor-existing-user').value='203';await e('instrutor-create-form').fire('submit');
assert.deepEqual(recordBodies,['{"usuario_id":203}']);

async function regressionI1() {
  await setup();
  await e('create-instrutor').fire('click');
  e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
  e('instrutor-existing-user').value='203';await e('instrutor-existing-user').fire('change');
  writeStatus=400;
  await e('instrutor-create-form').fire('submit');
  usersRaw=`[${userRaw()},${userRaw('203','Conta A',false)},${userRaw('205','Conta B')}]`;
  writeStatus=200;
  await e('instrutor-complete').fire('click');
  assert.match(e('instrutor-create-feedback').textContent,/não está mais elegível/);
  assert.equal(e('instrutor-create-mode').disabled,true);
  assert(e('instrutor-end-attempt'), 'I1: an ineligible pending registration needs an explicit exit');
  assert.equal(e('instrutor-end-attempt').hidden,false);
  await window.bootstrap.Modal.getInstance(e('instrutor-create-modal')).hide();
  await e('create-instrutor').fire('click');
  assert.equal(e('instrutor-end-attempt').hidden,false);
  const beforeEnding=calls.length;
  await e('instrutor-end-attempt').fire('click');
  assert.equal(calls.length,beforeEnding,'Ending a pending attempt must not issue any request');
  assert.equal(e('instrutor-create-mode').disabled,false);
  assert.equal(e('instrutor-create-mode').value,'new');
  assert.equal(e('instrutor-new-fields').hidden,false);
  assert.equal(e('instrutor-create-submit').hidden,false);
  assert.equal(e('instrutor-complete').hidden,true);
  assert.equal(e('instrutor-end-attempt').hidden,true);
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(e('instrutor-existing-user').value,'');
  assert.equal(e('instrutor-create-feedback').textContent.includes('não está mais elegível'),false);
  assert.deepEqual(e('instrutor-existing-user').children.map(option=>option.value),['','205']);
  e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
  e('instrutor-existing-user').value='205';await e('instrutor-existing-user').fire('change');
  assert.equal(e('instrutor-create-submit').disabled,false);
  await e('instrutor-create-form').fire('submit');
  assert.deepEqual(recordBodies,['{"usuario_id":203}','{"usuario_id":205}']);
  assert.equal(calls.filter(call=>call.method==='POST'&&call.url==='/api/usuarios').length,0);
  assert.equal(calls.some(call=>call.method==='PUT'||call.method==='DELETE'),false);
  assert.match(e('instrutores-feedback').textContent,/sucesso/);

  // Recovery must remain reachable when subsequent metadata/list reads fail.
  // Ending the local attempt must not clear uncertainty about a previous write.
  await setup();await newAccount();
  const original=globalThis.fetch;
  globalThis.fetch=(url,options)=>url==='/api/instrutores'&&options.method==='POST'
    ? Promise.resolve(response('SQL',500)) : original(url,options);
  await e('instrutor-create-form').fire('submit');
  await window.bootstrap.Modal.getInstance(e('instrutor-create-modal')).hide();
  mode='profile-error';await module.loadInstrutores();
  assert.equal(e('create-instrutor').disabled,false);
  await e('create-instrutor').fire('click');
  assert.equal(e('instrutor-end-attempt').hidden,false);
  assert.equal(document.activeElement.id,'instrutor-end-attempt');
  await window.bootstrap.Modal.getInstance(e('instrutor-create-modal')).hide();
  mode=500;await module.loadInstrutores();
  await e('create-instrutor').fire('click');
  assert.equal(e('instrutor-create-modal').hidden,false);
  assert.equal(e('instrutor-end-attempt').hidden,false);
  const beforeCancel=calls.length;
  await e('instrutor-end-attempt').fire('click');
  assert.equal(calls.length,beforeCancel);
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(e('instrutor-create-mode').disabled,false);
  mode='normal';await module.loadInstrutores();
  assert.equal(e('instrutor-create-submit').disabled,false);
}

async function regressionI2() {
  await setup();
  await e('create-instrutor').fire('click');
  e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
  e('instrutor-existing-user').value='203';await e('instrutor-existing-user').fire('change');
  e('instrutor-create-mode').value='new';await e('instrutor-create-mode').fire('change');
  assert.equal(e('instrutor-existing-user').value,'');
  await newAccount();mode='transport';
  await e('instrutor-create-form').fire('submit');
  assert.equal(e('instrutor-create-password').value,'');
  usersRaw=`[${userRaw()},${userRaw('203','Conta A')},${userRaw('205','Conta B')},${userRaw('206','Outra conta')}]`;
  mode='normal';await e('instrutor-reconcile').fire('click');
  assert.equal(e('instrutor-create-mode').value,'existing');
  assert.equal(e('instrutor-existing-user').value,'','I2: reconciliation must discard a previous unrelated selection');
  assert.equal(e('instrutor-create-submit').disabled,true);
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(calls.filter(call=>call.url==='/api/instrutores'&&call.method==='POST').length,0);
  await e('instrutor-create-form').fire('submit');
  assert.equal(calls.filter(call=>call.url==='/api/instrutores'&&call.method==='POST').length,0);
  await window.bootstrap.Modal.getInstance(e('instrutor-create-modal')).hide();
  await e('create-instrutor').fire('click');
  assert.equal(e('instrutor-existing-user').value,'');
  assert.equal(e('instrutor-create-submit').disabled,true);
  e('instrutor-existing-user').value='205';await e('instrutor-existing-user').fire('change');
  assert.equal(e('instrutor-create-submit').disabled,false);
  await e('instrutor-create-form').fire('submit');
  assert.deepEqual(recordBodies.slice(1),['{"usuario_id":205}']);
  assert.equal(calls.filter(call=>call.url==='/api/usuarios'&&call.method==='POST').length,1);
  assert.match(e('instrutores-feedback').textContent,/sucesso/);
}

await regressionI1();
await regressionI2();

// A timed-out Instrutor write may already exist. Reconciliation must finish without
// another POST, including after a concurrent request returns 409.
for(const failure of ['transport',409]) {
  await setup();await e('create-instrutor').fire('click');
  e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
  e('instrutor-existing-user').value='203';
  if(failure==='transport')mode='transport';else writeStatus=failure;
  await e('instrutor-create-form').fire('submit');
  assert.equal(e('instrutor-complete').hidden,false);
  const postCount=calls.filter(call=>call.method==='POST').length;
  listRaw=`[${instrutorRaw()},${instrutorRaw('302','203')}]`;mode='normal';writeStatus=200;
  await e('instrutor-complete').fire('click');
  assert.equal(calls.filter(call=>call.method==='POST').length,postCount);
  assert.match(e('instrutores-feedback').textContent,/sucesso/);
}

for(const status of [400,403,404,409,500]) {
  await setup();await newAccount();writeStatus=status;
  await e('instrutor-create-form').fire('submit');
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(calls.filter(call=>call.url==='/api/instrutores'&&call.method==='POST').length,0);
  assert.equal(e('instrutor-create-feedback').textContent.includes('SQL'),false);
}

for(const id of limits) {
  await setup();listRaw=`[${instrutorRaw(id,id)}]`;usersRaw=`[${userRaw(id)}]`;await module.loadInstrutores();
  await rowButtons()[0].fire('click');assert.equal(e('instrutor-edit-name').value,'Instrutor real');
  e('instrutor-edit-name').value='Nome alterado';await e('instrutor-edit-form').fire('submit');
  assert.equal(calls.at(-1).url,`/api/usuarios/${id}`);
  assert.equal(recordBodies.at(-1),'{"nome":"Nome alterado","email":"instrutor@example.test"}');
  assert.match(e('instrutores-rows').textContent,/Nome alterado/);
  await rowButtons()[1].fire('click');await e('instrutor-status-submit').fire('click');
  assert.equal(calls.at(-1).url,`/api/usuarios/${id}/status`);assert.equal(recordBodies.at(-1),'{"ativo":false}');
  assert.match(e('instrutores-rows').textContent,/Inativo/);assert.equal(rowButtons()[1].textContent,'Ativar');
  await rowButtons()[1].fire('click');await e('instrutor-status-submit').fire('click');
  assert.equal(recordBodies.at(-1),'{"ativo":true}');assert.equal(e('instrutores-rows').children.length,1);
}
for(const operation of ['edit','status']) for(const status of [400,403,404,409,500,'transport']) {
  await setup();await rowButtons()[operation==='edit'?0:1].fire('click');
  if(status==='transport')mode='transport';else writeStatus=status;
  await e(operation==='edit'?'instrutor-edit-form':'instrutor-status-submit').fire(operation==='edit'?'submit':'click');
  assert.equal(e('instrutores-rows').textContent.includes('Instrutor real'),true);
  assert.equal(e(`instrutor-${operation}-feedback`).textContent.includes('SQL'),false);
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
  const target=e(operation==='edit'?'instrutor-edit-form':'instrutor-status-submit');
  const event=operation==='edit'?'submit':'click';
  const inFlight=target.fire(event);await target.fire(event);await module.loadInstrutores();
  assert.equal(puts,1);assert.equal(e('refresh-instrutores').disabled,true);
  assert.equal(e('instrutores-rows').textContent.includes('Inativo'),false);
  await releasePut();await inFlight;
  assert.equal(e('refresh-instrutores').disabled,false);
}
await setup();await newAccount();let resolvePost;
const underlying=globalThis.fetch;
globalThis.fetch=(url,options)=>url==='/api/usuarios'?new Promise(resolve=>{resolvePost=()=>resolve(response(userRaw('205'),201));}):underlying(url,options);
const submit=e('instrutor-create-form').fire('submit');await e('instrutor-create-form').fire('submit');
assert.equal(e('instrutor-create-submit').disabled,true);assert.equal(e('instrutor-create-password').value,'');
assert.equal((await e('instrutor-create-modal').fire('hide.bs.modal')).prevented,true);
resolvePost();await submit;

await setup();
const attack='<script>alert(1)</script><img src=x onerror=alert(1)> " \' & < >';
usersRaw=`[${userRaw('201',attack)}]`;await module.loadInstrutores();
assert(e('instrutores-rows').textContent.includes(attack));assert.equal(e('instrutores-rows').querySelectorAll('script, img').length,0);
await rowButtons()[1].fire('click');assert(e('instrutor-status-question').textContent.includes(attack));
assert.equal(e('instrutor-status-question').querySelectorAll('script, img').length,0);
usersRaw=`[${userRaw('201',attack).replace('"instrutor@example.test"',JSON.stringify(attack))}]`;
await module.loadInstrutores();assert(e('instrutores-rows').children[0].children[1].textContent.includes(attack));
assert.equal(e('instrutores-rows').querySelectorAll('script, img').length,0);

// A current Aluno profile does not hide a historical Instrutor or block edits.
// Distinct identifiers prove that account writes never use Instrutor.id.
await setup();
listRaw=`[${instrutorRaw('9007199254740993','203')}]`;
usersRaw=`[${userRaw('203','Histórico',false,'91')}]`;
await module.loadInstrutores();
assert.equal(e('instrutores-rows').children.length,1);
assert.equal(rowButtons()[0].disabled,false);
assert.equal(rowButtons()[1].textContent,'Ativar');
await rowButtons()[0].fire('click');
await e('instrutor-edit-form').fire('submit');
assert.equal(calls.at(-1).url,'/api/usuarios/203');
await rowButtons()[1].fire('click');
await e('instrutor-status-submit').fire('click');
assert.equal(calls.at(-1).url,'/api/usuarios/203/status');

// Any successful refresh discards an existing-account selection (I2).
await setup();await e('create-instrutor').fire('click');
e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
e('instrutor-existing-user').value='203';await e('instrutor-existing-user').fire('change');
await module.loadInstrutores();
assert.equal(e('instrutor-existing-user').value,'');
assert.equal(e('instrutor-create-submit').disabled,true);

// History is not an eligibility dimension. No Aluno or TH-30 endpoint is read.
await setup();
assert.deepEqual(calls.map(call=>call.url).sort(),
  ['/api/instrutores','/api/perfis',`/api/usuarios?academia_id=${academy}`].sort());
assert(e('instrutor-existing-user').children.some(option=>option.value==='203'));

// Compare the authenticated ID exactly at every supported int64 magnitude.
// Exercise the module's existing-account POST, not only the shared serializer.
for(const id of limits) {
  await setup();usersRaw=`[${userRaw()},${userRaw(id,'Conta elegível')}]`;
  await module.loadInstrutores();await e('create-instrutor').fire('click');
  e('instrutor-create-mode').value='existing';await e('instrutor-create-mode').fire('change');
  e('instrutor-existing-user').value=id;await e('instrutor-existing-user').fire('change');
  await e('instrutor-create-form').fire('submit');
  assert.deepEqual(recordBodies,[`{"usuario_id":${id}}`]);
  assert.equal(e('instrutores-rows').children.length,2);
  assert.match(e('instrutores-rows').textContent,/Conta elegível/);
}

// Compare the authenticated ID exactly at every supported int64 magnitude.
for(const id of limits) {
  await setup();module.initInstrutores({...actor,userId:id});
  listRaw=`[${instrutorRaw('501',id)}]`;usersRaw=`[${userRaw(id)}]`;
  await module.loadInstrutores();
  assert.equal(rowButtons()[1].disabled,true);
  assert.equal(rowButtons()[0].disabled,false);
  await rowButtons()[1].fire('click');
  await e('instrutor-status-submit').fire('click');
  assert.equal(calls.some(call=>call.method==='PUT'),false);
}

// Profiles must match the canonical name, including case and whitespace.
for(const name of ['instrutor','INSTRUTOR','Instrutor ','Instructor']) {
  await setup();profileRaw=`[{"id":${profileId},"nome":${JSON.stringify(name)},"ativo":1}]`;
  await module.loadInstrutores();assert.equal(e('create-instrutor').disabled,true);
  assert.equal(e('instrutores-rows').children.length,1);
}

// Reject malformed snapshots rather than merging foreign or duplicate accounts.
for(const broken of ['duplicate-record','duplicate-user','foreign-user','invalid-id','invalid-status']) {
  await setup();
  if(broken==='duplicate-record')listRaw=`[${instrutorRaw()},${instrutorRaw()}]`;
  if(broken==='duplicate-user')usersRaw=`[${userRaw()},${userRaw()}]`;
  if(broken==='foreign-user')usersRaw=`[${userRaw().replace(`"academia_id":${academy}`,'"academia_id":2')}]`;
  if(broken==='invalid-id')listRaw='[{"id":9223372036854775808,"usuario_id":201,"criado_em":"x"}]';
  if(broken==='invalid-status')usersRaw=`[${userRaw().replace('"ativo":true','"ativo":1')}]`;
  await module.loadInstrutores();
  assert.equal(e('instrutores-error').hidden,false);
  assert.equal(e('create-instrutor').disabled,true);
  assert.equal(calls.some(call=>call.method==='POST'),false);
}

// Invalid write responses remain ambiguous and cannot cause automatic retries.
for(const operation of ['create','edit','status']) {
  await setup();
  if(operation==='create')await newAccount();
  else await rowButtons()[operation==='edit'?0:1].fire('click');
  mode='invalid-write';
  await e(operation==='create'?'instrutor-create-form':operation==='edit'?'instrutor-edit-form':'instrutor-status-submit')
    .fire(operation==='status'?'click':'submit');
  const writes=calls.filter(call=>['POST','PUT'].includes(call.method)).length;
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls.filter(call=>['POST','PUT'].includes(call.method)).length,writes);
  assert.match(e(`instrutor-${operation}-feedback`).textContent,/não pôde ser confirmado/);
  assert.equal(e('instrutor-create-password').value,'');
}

// Syntactically valid but incompatible successful responses are ambiguous too.
for(const target of ['account','record']) {
  await setup();await newAccount();const original=globalThis.fetch;
  globalThis.fetch=(url,options)=>options.method==='POST'&&url===(target==='account'?'/api/usuarios':'/api/instrutores')
    ? Promise.resolve(response('{}',201)) : original(url,options);
  await e('instrutor-create-form').fire('submit');
  assert.equal(e('instrutor-create-submit').hidden,true);
  assert.equal(e('instrutor-create-password').value,'');
  assert.equal(e('instrutor-complete').hidden,target==='account');
  assert.equal(calls.filter(call=>call.url==='/api/usuarios'&&call.method==='POST').length,target==='account'?0:1);
}

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
    if(url==='/api/instrutores')return response('[]');
    if(url.startsWith('/api/usuarios'))return response('[]');
    if(url==='/api/perfis')return response(profileRaw);
    return response('{}');
  };
  let instrutorSource=(await readFile('public/js/instrutores.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL));
  const instrutorURL='data:text/javascript;base64,'+Buffer.from(instrutorSource+'\n// '+sequence++).toString('base64');
  let appSource=(await readFile('public/js/app.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL))
    .replace("'./instrutores.js'",JSON.stringify(instrutorURL))
    .replace("'./alunos.js'",JSON.stringify('data:text/javascript,export function initAlunos(){};export function visitAlunos(){}'))
    .replace("'./academias.js'",JSON.stringify('data:text/javascript,export function loadAcademias(){}'));
  await import('data:text/javascript;base64,'+Buffer.from(appSource+'\n// '+sequence++).toString('base64'));
  assert.deepEqual(order,['/api/auth/me']);releaseAuth();
  for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(order.includes('/api/instrutores'),status===200);
  assert.equal(document.title,'Instrutores | TrainingHub');
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
        raise RuntimeError("TH-32 critical int64/JavaScript checks NOT EXECUTED: install Node; this suite cannot pass without them.")
    markup = Markup()
    markup.feed((ROOT / "public/index.html").read_text(encoding="utf-8"))
    script = JS.replace("__MARKUP__", json.dumps(markup.root, ensure_ascii=True))
    result = subprocess.check_output([node, "--input-type=module", "-"], input=script,
                                     text=True, encoding="utf-8", cwd=ROOT)
    report = json.loads(result)
    print(f"TH-32 JavaScript/DOM: {report['checks']} assertions passed; int64/parser/serializer, list/join, states, registration/recovery, edit/status, XSS, auth ordering. Not visual proof.", flush=True)
    return report["bodies"]


def check_http(bodies):
    env = dict(os.environ)
    env["PATH"] = str(ROOT / "build") + os.pathsep + env["PATH"]
    encoded = subprocess.check_output([str(ROOT / "build/security-tests/security_tests.exe"),
                                       "--fixture-hash"], env=env, text=True).strip()
    checked = 0
    with tempfile.TemporaryDirectory(prefix="th32-", dir=ROOT / "build") as temporary:
        directory = Path(temporary)
        database = directory / "instrutores.db"
        with closing(sqlite3.connect(database)) as db:
            for migration in sorted((ROOT / "migrations").glob("*.sql")):
                db.executescript(migration.read_text(encoding="utf-8"))
            db.execute("INSERT INTO academia(id,nome) VALUES(1,'Tenant de teste')")
            insert_admin(db, encoded)
            profile = db.execute("SELECT id FROM perfil WHERE nome='Instrutor'").fetchone()[0]
            for identity in [1, 2**40, 9007199254740993]:
                db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) VALUES(?,1,?,'Instrutor',?,?)",
                           (identity, profile, f"u{identity}@example.test", encoded))
            # A former Aluno now has the Instrutor profile. Both histories may coexist.
            db.execute("INSERT INTO aluno(usuario_id) VALUES(1)")
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
                            raise RuntimeError("TH-32 isolated server exited before readiness")
                        time.sleep(.1)
                else:
                    raise RuntimeError("TH-32 isolated server unavailable")
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
                    "nome": "Conta criada pela interface", "email": "nova.th32@example.test",
                    "senha": "TH32-test-password"}, 201)
                # Exercise a confirmed account with an initially rejected registration.
                request("PUT", f"/api/usuarios/{new_account['id']}/status", {"ativo": False})
                request("POST", "/api/instrutores", {"usuario_id": new_account["id"]}, 400)
                request("PUT", f"/api/usuarios/{new_account['id']}/status", {"ativo": True})
                created = request("POST", "/api/instrutores", {"usuario_id": new_account["id"]}, 201)
                assert set(created) == {"id", "usuario_id", "criado_em"}
                request("POST", "/api/instrutores", {"usuario_id": new_account["id"]}, 409)
                # Seed INT64_MAX only after POST Usuario: SQLite AUTOINCREMENT
                # cannot create another account once that maximum row exists.
                with closing(sqlite3.connect(database)) as db:
                    db.execute("INSERT INTO usuario(id,academia_id,perfil_id,nome,email,senha_hash) VALUES(?,1,?,'Limite',?,?)",
                               (2**63-1, profile, "max@example.test", encoded))
                    db.commit()
                records = []
                for body in bodies:
                    identity = json.loads(body)["usuario_id"]
                    instrutor = request("POST", "/api/instrutores", body, 201)
                    assert instrutor["usuario_id"] == identity
                    assert request("GET", f"/api/instrutores/{instrutor['id']}") == instrutor
                    updated = request("PUT", f"/api/usuarios/{identity}", {"nome": "Editado", "email": f"edit{identity}@example.test"})
                    assert updated["id"] == identity
                    assert request("PUT", f"/api/usuarios/{identity}/status", {"ativo": False})["ativo"] is False
                    assert any(row["usuario_id"] == identity for row in request("GET", "/api/instrutores"))
                    assert request("PUT", f"/api/usuarios/{identity}/status", {"ativo": True})["ativo"] is True
                    records.append((identity, instrutor["id"]))
                # Test public Instrutor IDs independently from account IDs. Writes above
                # are complete before this fixture introduces the maximum row ID.
                with closing(sqlite3.connect(database)) as db:
                    db.execute("UPDATE instrutor SET id=10 WHERE id=?", (created["id"],))
                    for identity, generated in records:
                        db.execute("UPDATE instrutor SET id=? WHERE id=?", (identity, generated))
                    db.execute("UPDATE usuario SET perfil_id=(SELECT id FROM perfil WHERE nome='Aluno'), ativo=0 WHERE id=1")
                    db.commit()
                for identity, _ in records:
                    exact = request("GET", f"/api/instrutores/{identity}")
                    assert exact["id"] == identity and exact["usuario_id"] == identity
                historical = request("GET", "/api/instrutores/1")
                assert historical["usuario_id"] == 1
                request("PUT", "/api/usuarios/1", {"nome": "Histórico editado", "email": "history@example.test"})
                request("PUT", "/api/usuarios/1/status", {"ativo": True})
                with closing(sqlite3.connect(database)) as db:
                    assert db.execute("SELECT COUNT(*) FROM aluno WHERE usuario_id=1").fetchone()[0] == 1
                    assert db.execute("SELECT COUNT(*) FROM instrutor WHERE usuario_id=1").fetchone()[0] == 1
                assert len(request("GET", "/api/instrutores")) == 5
                assert len(request("GET", "/api/usuarios?academia_id=1")) == 6
                assert any(item["nome"] == "Instrutor" for item in request("GET", "/api/perfis"))
                request("PUT", "/api/usuarios/100/status", {"ativo": False}, 403)
                with urllib.request.urlopen(base + "/js/instrutores.js") as result:
                    assert result.code == 200 and result.read()
                    checked += 1
            finally:
                server.terminate()
                server.wait(timeout=10)
    print(f"TH-32 real HTTP: {checked} requests passed with temporary SQLite; exact JS-generated int64 bodies accepted.", flush=True)


def run():
    development = ROOT / "data/traininghub.db"
    before = hashlib.sha256(development.read_bytes()).hexdigest() if development.exists() else None
    try:
        check_http(check_javascript())
    finally:
        after = hashlib.sha256(development.read_bytes()).hexdigest() if development.exists() else None
        assert before == after, "Development database changed"
    print("TH-32 development database unchanged.")


if __name__ == "__main__":
    run()
