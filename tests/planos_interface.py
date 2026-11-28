"""TH-39: exact money/days, delivered DOM behavior and isolated real HTTP.

Browser layout and keyboard proof runs through interface_web.py --browser.
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
import {readFile} from 'node:fs/promises';
let checks=0;
const assert=new Proxy(nativeAssert,{
  apply(target,self,args){checks++;return Reflect.apply(target,self,args);},
  get(target,key){const value=target[key];return typeof value==='function'?(...args)=>{checks++;return value(...args);}:value;},
});
const markup=__MARKUP__;
const apiSource=await readFile('public/js/api.js','utf8');
const apiURL='data:text/javascript;base64,'+Buffer.from(apiSource).toString('base64');
const api=await import(apiURL);
const source=(await readFile('public/js/planos.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL));
let sequence=0;
const moduleURL=()=> 'data:text/javascript;base64,'+Buffer.from(source+'\n// '+sequence++).toString('base64');
const conversions=await import(moduleURL());
const money=['0','1','99','100','9007199254740993','9223372036854775807'];
const days=['1','9007199254740993','9223372036854775807'];
const ids=['9007199254740991','9007199254740992','9223372036854775806','9223372036854775807'];
const bodies=[];
for(const value of money){
  const decimal=conversions.centavosParaReais(value);
  assert.equal(conversions.reaisParaCentavos(decimal),value);
  assert.equal(api.parseJson(`{"valor_centavos":${value}}`).valor_centavos,value);
  assert.equal(api.serializeBody({valor_centavos:value}),`{"valor_centavos":${value}}`);
}
for(const value of days){
  assert.equal(api.parseJson(`{"duracao_dias":${value}}`).duracao_dias,value);
  assert.equal(api.serializeBody({duracao_dias:value}),`{"duracao_dias":${value}}`);
}
for(const value of ids)assert.deepEqual(api.parseJson(`{"id":${value},"academia_id":${value}}`),{id:value,academia_id:value});
for(const [input,expected] of [['99','9900'],['99,9','9990'],['99,90','9990'],['99.90','9990'],['0','0'],['0,00','0'],[' 99,90 ','9990']])
  assert.equal(conversions.reaisParaCentavos(input),expected);
for(const input of ['-1','+1','1e2','1,234','1.234','1.234,56','1,234.56','1 00','abc','','.99','99,','92233720368547758,08'])
  assert.equal(conversions.reaisParaCentavos(input),null,input);
assert.equal(conversions.formatarValor('9223372036854775807'),'R$ 92.233.720.368.547.758,07');
for(const [value,expected] of [['0','R$ 0,00'],['1','R$ 0,01'],['99','R$ 0,99'],['100','R$ 1,00']])
  assert.equal(conversions.formatarValor(value),expected);
for(const field of ['valor_centavos','duracao_dias']){
  for(const token of ['-1','1.0','1e2','"1"','null','true','01','9223372036854775808'])
    assert.throws(()=>api.parseJson(`{"${field}":${token}}`),SyntaxError);
  for(const token of [1,1n,'01','-1','1.5','1e2','1,"injected":true','9223372036854775808'])
    assert.throws(()=>api.serializeBody({[field]:token}),error=>error.status===400);
}
assert.throws(()=>api.parseJson('{"duracao_dias":0}'),SyntaxError);
assert.throws(()=>api.serializeBody({duracao_dias:'0'}),error=>error.status===400);
assert.deepEqual(api.parseJson('{"unrelated":1.5,"other":0,"flag":true,"text":"valor_centavos:99"}'),
  {unrelated:1.5,other:0,flag:true,text:'valor_centavos:99'});

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
  reportValidity() { return this.querySelectorAll('input, select, textarea').every(input => input.validity.valid); }
  reset() { for (const input of this.querySelectorAll('input, select, textarea')) input.value=input.defaultValue; }
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
    constructor(element){this.element=element;this.shown=false;this.closing=false;}
    show(){if(this.shown||this.closing)return;this.shown=true;this.element.hidden=false;
      if(globalThis.deferModalShown){globalThis.releaseModalShown=()=>this.element.fire('shown.bs.modal');return;}
      return this.element.fire('shown.bs.modal');}
    async hide(){
      if(!this.shown||this.closing)return;
      const event=await this.element.fire('hide.bs.modal');
      if(event.prevented)return;
      this.shown=false;this.closing=true;
      const finish=async()=>{this.closing=false;this.element.hidden=true;await this.element.fire('hidden.bs.modal');};
      if(globalThis.deferModalHidden)this.finishHide=finish;
      else await finish();
    }
  }
  globalThis.window = {bootstrap:{Modal,Offcanvas:{getInstance(){return null;}}},addEventListener(){}};
  globalThis.location = {hash:'#alunos',destinations:[],replace(path){this.destinations.push(path);}};
  return document.getElementById;
}


const academy='9007199254740993';
const actor={userId:'100',academiaId:academy,perfilId:'90'};
const plan=(overrides={})=>({id:'9223372036854775806',academia_id:academy,nome:'Mensal',descricao:'Descrição completa',
  valor_centavos:'9990',duracao_dias:'30',ativo:true,criado_em:'2026-11-28 12:00:00',...overrides});
const response=(value,status=200)=>new Response(typeof value==='string'?value:JSON.stringify(value),{status});
const wire=(value)=>Array.isArray(value)?'['+value.map(wire).join(',')+']':api.serializeBody(value);
let e,module,calls,records,getMode,writeMode,releaseWrite;
const writes=()=>calls.filter(call=>call.method!=='GET');
async function tick(){for(let index=0;index<8;index++)await new Promise(resolve=>setImmediate(resolve));}
async function setup(values=[plan()],visit=true){
  e=fixture();location.hash='#planos';calls=[];getMode=null;writeMode=null;
  globalThis.deferModalShown=false;
  globalThis.deferModalHidden=false;
  records=new Map(values.map(value=>[value.id,value]));
  globalThis.fetch=async(url,options)=>{
    calls.push({url,...options});
    assert(!url.includes('?'),'Planos never sends tenant query');
    if(options.method==='GET'){
      if(getMode==='network')throw new TypeError('private SQL');
      if(getMode==='invalid')return response('{bad');
      if(typeof getMode==='number')return response('private SQL',getMode);
      if(url==='/api/planos')return response(wire([...records.values()]));
      const value=records.get(url.split('/')[3]);
      return value?response(wire(value)):response('{}',404);
    }
    if(typeof writeMode==='number')return response('private SQL',writeMode);
    if(writeMode==='network')throw new TypeError('private SQL');
    if(writeMode==='invalid')return response('{bad');
    const dto=api.parseJson(options.body);
    assert.deepEqual(Object.keys(dto).sort(),url.endsWith('/status')?['ativo']:['descricao','duracao_dias','nome','valor_centavos']);
    let saved;
    if(options.method==='POST')saved=plan({...dto,id:'201'});
    else {const id=url.split('/')[3];saved={...records.get(id),...dto};}
    records.set(saved.id,saved);
    if(writeMode==='committed')throw new TypeError('response lost after commit');
    if(writeMode==='hold')await new Promise(resolve=>{releaseWrite=resolve;});
    return response(wire(saved),options.method==='POST'?201:200);
  };
  module=await import(moduleURL());module.initPlanos(actor);
  if(visit)await module.visitPlanos();
  return module;
}
function fill(kind,overrides={}){
  const values={name:'  Novo Plano  ',description:'',value:'99,9',duration:'30',...overrides};
  for(const [field,value] of Object.entries(values)){
    e(`plano-${kind}-${field}`).value=value;
    void e(`plano-${kind}-${field}`).fire('input');
  }
}
const actions=()=>e('planos-rows').querySelectorAll('button').filter(button=>button.getAttribute('aria-label'));
async function close(kind){await window.bootstrap.Modal.getInstance(e(`plano-${kind}-modal`)).hide();await tick();}

await setup([],false);
let releaseList;
globalThis.fetch=()=>new Promise(resolve=>{releaseList=()=>resolve(response('[]'));});
const loading=module.visitPlanos();
assert.equal(e('planos-panel').getAttribute('aria-busy'),'true');
assert.match(e('planos-state').textContent,/Carregando/);
assert.equal(e('create-plano').disabled,true);releaseList();await loading;
assert.equal(e('planos-panel').getAttribute('aria-busy'),'false');
assert.match(e('planos-state').textContent,/Nenhum plano cadastrado/);
assert.equal(e('planos-empty-create').disabled,false);

for(const id of ids){await setup([plan({id,ativo:false})]);assert.match(e('planos-rows').textContent,/Inativo/);
  await actions()[0].fire('click');assert.equal(calls.at(-1).url,`/api/planos/${id}`);await close('edit');}

await setup();globalThis.deferModalShown=true;await actions()[0].fire('click');
assert.equal(e('plano-edit-submit').disabled,true);await globalThis.releaseModalShown();
assert.equal(document.activeElement.id,'plano-edit-name');assert.equal(e('plano-edit-submit').disabled,false);
await close('edit');

for(const [index,value] of money.entries()){
  await setup([]);await e('create-plano').fire('click');
  fill('create',{name:`Plano precisão ${index}`,value:conversions.centavosParaReais(value),duration:days[index%days.length],description:index%2?'  descrição preservada  ':''});
  await e('plano-create-form').fire('submit');await tick();
  const sent=writes()[0];assert.equal(sent.url,'/api/planos');
  const dto=api.parseJson(sent.body);assert.equal(dto.valor_centavos,value);assert.equal(dto.duracao_dias,days[index%days.length]);
  assert.equal(dto.descricao,index%2?'  descrição preservada  ':null);
  assert.match(e('planos-feedback').textContent,/cadastrado com sucesso/);bodies.push(sent.body);
}
await setup([]);await e('planos-empty-create')?.fire('click');
await e('create-plano').fire('click');fill('create');
for(const value of ['92233720368547758,08','1e2','1.234,56','-1','1.001']){
  e('plano-create-value').value=value;await e('plano-create-form').fire('submit');assert.equal(writes().length,0);
}
fill('create');for(const value of ['0','-1','1.5','1e2','01','9223372036854775808']){
  e('plano-create-duration').value=value;await e('plano-create-form').fire('submit');assert.equal(writes().length,0);
}
fill('create',{name:'   '});await e('plano-create-form').fire('submit');assert.equal(writes().length,0);

await setup([plan({ativo:false,descricao:''})]);await actions()[0].fire('click');
assert.equal(e('plano-edit-description').value,'');assert.equal(e('plano-edit-value').value,'99,90');
e('plano-edit-name').value='  Nome preservado  ';await e('plano-edit-form').fire('submit');await tick();
assert.equal(api.parseJson(writes()[0].body).descricao,'');assert.equal(api.parseJson(writes()[0].body).nome,'  Nome preservado  ');
assert.match(e('planos-rows').textContent,/Inativo/);
await actions()[0].fire('click');e('plano-edit-description').value='';await e('plano-edit-description').fire('input');
await e('plano-edit-form').fire('submit');await tick();assert.equal(api.parseJson(writes().at(-1).body).descricao,null);
await actions()[1].fire('click');assert.match(e('plano-status-question').textContent,/Ativar/);
await e('plano-status-submit').fire('click');await tick();assert.equal(writes().at(-1).body,'{"ativo":true}');
await actions()[1].fire('click');await e('plano-status-submit').fire('click');await tick();
assert.equal(writes().at(-1).body,'{"ativo":false}');

// A browser textarea normalizes CRLF for display; an untouched description stays exact on the wire.
await setup([plan({descricao:'Linha 1\r\nLinha 2'})]);await actions()[0].fire('click');
e('plano-edit-description').value='Linha 1\nLinha 2';
await e('plano-edit-form').fire('submit');await tick();
assert.equal(api.parseJson(writes()[0].body).descricao,'Linha 1\r\nLinha 2');

for(const status of [400,401,403,404,409,500,502,'network','invalid']){
  await setup();writeMode=status;await actions()[0].fire('click');fill('edit');
  await e('plano-edit-form').fire('submit');await tick();
  assert.equal(writes().length,1);assert(!root.textContent.includes('private SQL'));
  if(status===401)assert.deepEqual(location.destinations,['/login.html']);
  else if([500,502,'network','invalid'].includes(status))assert.equal(e('planos-uncertain').hidden,false);
  else assert.match(e('plano-edit-feedback').textContent,/Confira|Conflito|permissão|disponível/);
}
for(const failure of [401,403,404,409,500,502,'network','invalid']){
  await setup([],false);getMode=failure;await module.visitPlanos();
  if(failure===401)assert.deepEqual(location.destinations,['/login.html']);
  else {assert.equal(e('planos-error').hidden,false);assert.equal(e('planos-state').hidden,true);
    getMode=null;await e('retry-planos').fire('click');assert.match(e('planos-state').textContent,/Nenhum plano/);}
}

await setup([]);writeMode='committed';await e('create-plano').fire('click');fill('create');
await e('plano-create-form').fire('submit');await tick();assert.equal(writes().length,1);
assert.equal(e('create-plano').disabled,true);await e('planos-reconcile').fire('click');
assert.match(e('planos-uncertain-message').textContent,/não prova/);assert.equal(writes().length,1);
assert.equal(e('create-plano').disabled,true);writeMode=null;await e('planos-resume').fire('click');
assert.equal(e('create-plano').disabled,false);
for(const kind of ['edit','status']){
  await setup();writeMode='committed';await actions()[kind==='edit'?0:1].fire('click');
  if(kind==='edit'){fill('edit');await e('plano-edit-form').fire('submit');}
  else await e('plano-status-submit').fire('click');await tick();
  await e('planos-reconcile').fire('click');assert.match(e('planos-uncertain-message').textContent,/Estado observado/);
  assert.equal(writes().length,1);writeMode=null;await e('planos-resume').fire('click');assert.equal(writes().length,1);
}

await setup([]);writeMode='hold';await e('create-plano').fire('click');fill('create');
const held=e('plano-create-form').fire('submit');await tick();
await e('plano-create-form').fire('submit');assert.equal(writes().length,1);
assert.equal((await e('plano-create-modal').fire('hide.bs.modal')).prevented,true);
assert.equal(e('plano-create-submit').disabled,true);releaseWrite();await held;await tick();

const attack='<img src=x onerror=alert(1)><script>alert(1)</script>\"\'><svg/onload=alert(1)>';
await setup([plan({nome:attack,descricao:attack+'\n'.repeat(10)+'complete'})]);
assert(e('planos-rows').textContent.includes(attack));assert.equal(e('planos-rows').querySelectorAll('img, script, svg').length,0);
await actions()[0].fire('click');assert.equal(e('plano-edit-description').value,attack+'\n'.repeat(10)+'complete');await close('edit');
await actions()[1].fire('click');assert(e('plano-status-question').textContent.includes(attack));await close('status');

// A completed old request must not overwrite the new generation after leaving.
await setup([],false);let releaseStale;
globalThis.fetch=()=>new Promise(resolve=>{releaseStale=()=>resolve(response(wire([plan({nome:'stale'})])));});
const stale=module.visitPlanos();module.leavePlanos();
globalThis.fetch=async()=>response('[]');await module.visitPlanos();releaseStale();await stale;
assert.equal(e('planos-rows').children.length,0);assert.equal(e('planos-panel').getAttribute('aria-busy'),'false');

// Keep hide and hidden separate: cancellation must block every write during the animation.
for(const kind of ['create','edit','status']){
  await setup(kind==='create'?[]:[plan()]);globalThis.deferModalHidden=true;
  if(kind==='create')await e('create-plano').fire('click');
  else await actions()[kind==='edit'?0:1].fire('click');
  if(kind!=='status')fill(kind);
  const modal=window.bootstrap.Modal.getInstance(e(`plano-${kind}-modal`));
  await modal.hide();
  assert.equal(e(`plano-${kind}-submit`).disabled,true,`${kind} cannot submit after hide`);
  assert.equal(e('planos-panel').getAttribute('aria-busy'),'true');
  await e(kind==='status'?'plano-status-submit':`plano-${kind}-form`).fire(kind==='status'?'click':'submit');
  assert.equal(writes().length,0,`${kind} must not write during hide/hidden`);
  module.leavePlanos();module.leavePlanos();
  await modal.finishHide();await modal.hide();await module.visitPlanos();
  assert.equal(e('planos-panel').getAttribute('aria-busy'),'false');
  assert.equal(e('refresh-planos').disabled,false);
  assert.equal(e('create-plano').disabled,false);
  if(kind==='create')await e('create-plano').fire('click');
  else await actions()[kind==='edit'?0:1].fire('click');
  assert.equal(e(`plano-${kind}-submit`).disabled,false,`${kind} reopens`);
  if(kind!=='status')fill(kind);
  await e(kind==='status'?'plano-status-submit':`plano-${kind}-form`).fire(kind==='status'?'click':'submit');
  await tick();assert.equal(writes().length,1);
  await modal.finishHide();await tick();
  assert.equal(e('refresh-planos').disabled,false);
  assert.equal(e('create-plano').disabled,false);
}

// Leaving during opening waits for shown exactly once, then finishes the same close lifecycle.
await setup();globalThis.deferModalShown=true;globalThis.deferModalHidden=true;
await actions()[0].fire('click');module.leavePlanos();module.leavePlanos();
await globalThis.releaseModalShown();await tick();
const openingModal=window.bootstrap.Modal.getInstance(e('plano-edit-modal'));
assert.equal(openingModal.closing,true);assert.equal(e('plano-edit-submit').disabled,true);
await openingModal.finishHide();await module.visitPlanos();
assert.equal(e('refresh-planos').disabled,false);assert.equal(e('create-plano').disabled,false);

// A write already sent still prevents cancellation; its response starts the actual hide.
for(const kind of ['create','edit','status']){
  await setup(kind==='create'?[]:[plan()]);globalThis.deferModalHidden=true;writeMode='hold';
  if(kind==='create')await e('create-plano').fire('click');
  else await actions()[kind==='edit'?0:1].fire('click');
  if(kind!=='status')fill(kind);
  const target=e(kind==='status'?'plano-status-submit':`plano-${kind}-form`);
  const sending=target.fire(kind==='status'?'click':'submit');await tick();
  const modal=window.bootstrap.Modal.getInstance(e(`plano-${kind}-modal`));
  await modal.hide();assert.equal(modal.shown,true);assert.equal(modal.closing,false);
  assert.equal(writes().length,1);
  releaseWrite();await sending;await tick();assert.equal(modal.closing,true);
  await modal.finishHide();await tick();assert.equal(e('refresh-planos').disabled,false);
  assert.equal(e('create-plano').disabled,false);
}

// Successful/ambiguous responses close asynchronously; known errors keep the form usable.
for(const outcome of [null,400,409,500,502,'network']){
  await setup([]);globalThis.deferModalHidden=true;writeMode=outcome;
  await e('create-plano').fire('click');fill('create');
  await e('plano-create-form').fire('submit');await tick();
  const modal=window.bootstrap.Modal.getInstance(e('plano-create-modal'));
  if(outcome===400||outcome===409){
    assert.equal(modal.closing,false);assert.equal(e('plano-create-submit').disabled,false);
    writeMode=null;await e('plano-create-form').fire('submit');await tick();
    assert.equal(writes().length,2);
  }else assert.equal(writes().length,1);
  assert.equal(modal.closing,true);
  await modal.finishHide();await modal.hide();await tick();
  assert.equal(e('refresh-planos').disabled,false);
  assert.equal(e('planos-panel').getAttribute('aria-busy'),'false');
  if(outcome!==null&&outcome!==400&&outcome!==409){
    assert.equal(e('planos-reconcile').disabled,false);
    await e('planos-reconcile').fire('click');
    assert.equal(e('planos-resume').hidden,false);assert.equal(writes().length,1);
    await e('planos-resume').fire('click');
  }
  assert.equal(e('create-plano').disabled,false);
  await e('create-plano').fire('click');assert.equal(e('plano-create-submit').disabled,false);
  await close('create');await modal.finishHide();
}

// Import the actual app graph; Planos cannot load before authentication settles.
for(const status of [200,401,403]){
  fixture();location.hash='#planos';let releaseAuth;const order=[];
  globalThis.fetch=async(url)=>{order.push(url);if(url==='/api/auth/me')return new Promise(resolve=>{
    releaseAuth=()=>resolve(response(status===200?api.serializeBody(actor):'{}',status));});
    return response(url==='/api/planos'?'[]':'{}');};
  let app=(await readFile('public/js/app.js','utf8')).replace("'./api.js'",JSON.stringify(apiURL))
    .replace("'./planos.js'",JSON.stringify(moduleURL()))
    .replace("'./alunos.js'",JSON.stringify('data:text/javascript,export function initAlunos(){};export function visitAlunos(){}'))
    .replace("'./instrutores.js'",JSON.stringify('data:text/javascript,export function initInstrutores(){};export function visitInstrutores(){}'))
    .replace("'./academias.js'",JSON.stringify('data:text/javascript,export function loadAcademias(){}'));
  await import('data:text/javascript;base64,'+Buffer.from(app+'\n// '+sequence++).toString('base64'));
  assert.deepEqual(order,['/api/auth/me']);releaseAuth();await tick();
  assert.equal(order.includes('/api/planos'),status===200);assert.equal(document.title,'Planos | TrainingHub');
  if(status===401)assert.deepEqual(location.destinations,['/login.html']);
}
console.log(JSON.stringify({checks,bodies}));
'''


def check_javascript():
    node = shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
    markup = Markup()
    markup.feed((ROOT / 'public/index.html').read_text(encoding='utf-8'))
    script = JS.replace('__MARKUP__', json.dumps(markup.root, ensure_ascii=True))
    result = subprocess.run([node, '--input-type=module', '-'], input=script, text=True,
                            encoding='utf-8', cwd=ROOT, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-4500:])
    report = json.loads(result.stdout)
    print(f"TH-39 JavaScript/DOM: {report['checks']} assertions passed; exact int64, money, states, CRUD/status, ambiguous writes, XSS and auth ordering.", flush=True)
    return report['bodies']


def check_http(bodies):
    env = dict(os.environ)
    env['PATH'] = str(ROOT / 'build') + os.pathsep + env['PATH']
    encoded = subprocess.check_output([str(ROOT / 'build/security-tests/security_tests.exe'), '--fixture-hash'], env=env, text=True).strip()
    checked = 0
    with tempfile.TemporaryDirectory(prefix='th39-', dir=ROOT / 'build') as temporary:
        directory = Path(temporary)
        database = directory / 'planos.db'
        with closing(sqlite3.connect(database)) as db:
            for migration in sorted((ROOT / 'migrations').glob('*.sql')):
                db.executescript(migration.read_text(encoding='utf-8'))
            db.executemany('INSERT INTO academia(id,nome) VALUES(?,?)', [(1,'A'),(2,'B')])
            insert_admin(db, encoded)
            insert_admin(db, encoded, 2, 110, 'b@example.test')
            db.commit()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        config['listeners'] = [{'address':'127.0.0.1','port':port}]
        config['db_clients'][0]['filename'] = database.as_posix()
        config['app']['document_root'] = (ROOT / 'public').as_posix()
        (directory / 'config.json').write_text(json.dumps(config), encoding='utf-8')
        base = f'http://127.0.0.1:{port}'
        with (directory / 'server.log').open('w+b') as log:
            server = subprocess.Popen([str(ROOT / 'build/traininghub.exe')], cwd=directory, env=env,
                                      stdout=log, stderr=log, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(base+'/api/health', timeout=1):
                            break
                    except OSError:
                        assert server.poll() is None
                        time.sleep(.05)
                else:
                    raise RuntimeError('TH-39 server unavailable')
                client = login_client(base)
                other = login_client(base, 2, 'b@example.test')

                def request(method, path, body=None, status=200, actor=None):
                    nonlocal checked
                    data = body.encode() if isinstance(body,str) else json.dumps(body).encode() if body is not None else None
                    req = urllib.request.Request(base+path, method=method, data=data, headers={'Content-Type':'application/json'})
                    try:
                        result = (actor or client).open(req,timeout=15)
                    except urllib.error.HTTPError as error:
                        result = error
                    with result:
                        content = result.read()
                        assert result.code == status, (path,result.code,status,content)
                        assert result.headers.get('Cache-Control') == 'no-store'
                        assert b'senha_hash' not in content and b'$argon2' not in content
                        checked += 1
                        return json.loads(content)

                assert request('GET','/api/planos') == []
                for body in bodies:
                    dto = json.loads(body)
                    assert set(dto) == {'nome','descricao','valor_centavos','duracao_dias'}
                    saved = request('POST','/api/planos',body,201)
                    assert all(saved[key] == value for key,value in dto.items())
                    path = f'/api/planos/{saved["id"]}'
                    assert request('GET',path) == saved
                    assert request('PUT',path,body) == saved
                    inactive = request('PUT',path+'/status',{'ativo':False})
                    assert inactive['ativo'] is False
                    assert request('PUT',path+'/status',{'ativo':False}) == inactive
                    assert request('PUT',path,body)['ativo'] is False
                    assert request('PUT',path+'/status',{'ativo':True})['ativo'] is True
                    with closing(sqlite3.connect(database)) as db:
                        assert db.execute('SELECT valor_centavos,duracao_dias FROM plano WHERE id=?',(saved['id'],)).fetchone() == (dto['valor_centavos'],dto['duracao_dias'])
                    request('GET',path,status=404,actor=other)
                assert request('GET','/api/planos',actor=other) == []
                # Seed maximum IDs only after all successful creates are complete.
                for index,identity in enumerate([9007199254740991,9007199254740992,9223372036854775806,9223372036854775807],1):
                    with closing(sqlite3.connect(database)) as db:
                        db.execute('UPDATE plano SET id=? WHERE id=?',(identity,index))
                        db.commit()
                    path=f'/api/planos/{identity}'
                    assert request('GET',path)['id'] == identity
                    assert request('PUT',path,bodies[index-1])['id'] == identity
                    assert request('PUT',path+'/status',{'ativo':False})['id'] == identity
                with closing(sqlite3.connect(database)) as db:
                    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
                with urllib.request.urlopen(base+'/js/planos.js') as result:
                    assert result.code == 200 and result.read()
            finally:
                if server.poll() is None:
                    server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
    print(f'TH-39 real HTTP: {checked} checks passed; JS-generated numeric tokens, SQLite persistence, edit/status, int64 and tenant isolation.',flush=True)


def run():
    development = ROOT / 'data/traininghub.db'
    before = hashlib.sha256(development.read_bytes()).digest()
    try:
        check_http(check_javascript())
    finally:
        assert hashlib.sha256(development.read_bytes()).digest() == before, 'Development database changed'
    print('TH-39 development database unchanged.')


if __name__ == '__main__':
    run()
