"""TH-33: delivered HTML/JavaScript, lossless IDs and modal lifecycle.

No npm or browser dependency. Real rendering/keyboard coverage lives in
interface_web.py --browser. Mutations run only in memory, never on source files.
"""

from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


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
let checks=0;
const assert=new Proxy(nativeAssert,{
  apply(target,self,args){checks++;return Reflect.apply(target,self,args);},
  get(target,key){const value=target[key];return typeof value==='function'?(...args)=>{checks++;return value(...args);}:value;},
});
const markup=__MARKUP__;
const apiSource=await readFile('public/js/api.js','utf8');
const apiURL='data:text/javascript;base64,'+Buffer.from(apiSource).toString('base64');
const api=await import(apiURL);
const response=(data,status=200)=>new Response(typeof data==='string'?data:JSON.stringify(data),{status});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
class Element {
  constructor(tag,attrs={}) {
    this.tagName=tag;this.attributes={...attrs};this.children=[];this.listeners={};
    this.id=attrs.id||'';this.value=attrs.value||'';this.defaultValue=this.value;
    this.disabled='disabled' in attrs;this.hidden='hidden' in attrs;this.required='required' in attrs;
    this.type=attrs.type;this.dataset={};this.isConnected=true;
    for(const [key,value] of Object.entries(attrs))if(key.startsWith('data-'))this.dataset[key.slice(5)]=value;
    this.classList={toggle(){},add(){},remove(){},contains(){return false;}};
  }
  append(...children){for(const child of children){if(child.tagName==='fragment')this.append(...child.children);else{this.children.push(child);if(typeof child!=='string')child.parent=this;}}}
  replaceChildren(...children){for(const child of this.children)if(typeof child!=='string')child.isConnected=false;this.children=[];this.append(...children);}
  set textContent(value){this.replaceChildren(String(value));}
  get textContent(){return this.children.map(child=>typeof child==='string'?child:child.textContent).join('');}
  set innerHTML(value){throw Error('Unsafe HTML sink');}
  insertAdjacentHTML(){throw Error('Unsafe HTML sink');}
  addEventListener(type,callback,options){(this.listeners[type]||=[]).push({callback,once:options?.once});}
  async fire(type){const event={target:this,currentTarget:this,prevented:false,preventDefault(){this.prevented=true;}};
    for(const handler of [...(this.listeners[type]||[])]){if(handler.once)this.listeners[type]=this.listeners[type].filter(item=>item!==handler);await handler.callback(event);}return event;}
  querySelectorAll(selector){const result=[];for(const child of this.children)if(typeof child!=='string'){if(selector.split(',').map(s=>s.trim()).includes(child.tagName))result.push(child);result.push(...child.querySelectorAll(selector));}return result;}
  setAttribute(key,value){this.attributes[key]=value;}
  getAttribute(key){return this.attributes[key];}
  removeAttribute(key){delete this.attributes[key];}
  focus(){document.activeElement=this;}
  setCustomValidity(value){this.validation=value;}
  get validity(){return {valid:this.disabled||(!this.validation&&(!this.required||!!this.value))};}
  reportValidity(){return this.querySelectorAll('input, select').every(item=>item.validity.valid);}
  reset(){for(const item of this.querySelectorAll('input, select'))item.value=item.defaultValue;}
}
let root;
function fixture(){
  function build(node){if(typeof node==='string')return node;const result=new Element(node.tag,node.attrs);result.append(...node.children.map(build));return result;}
  root=build(markup);
  function all(){const nodes=[];function walk(node){if(typeof node==='string')return;nodes.push(node);node.children.forEach(walk);}walk(root);return nodes;}
  globalThis.document={getElementById(id){return all().find(item=>item.id===id)||null;},createElement(tag){return new Element(tag);},createDocumentFragment(){return new Element('fragment');},querySelectorAll(){return [];}};
  const instances=new Map();
  class Modal {
    static getInstance(element){return instances.get(element);}
    static getOrCreateInstance(element){if(!instances.has(element))instances.set(element,new Modal(element));return instances.get(element);}
    constructor(element){this.element=element;this.closing=false;this.deferHide=false;}
    show(){if(this.closing)return;this.element.hidden=false;return this.element.fire('shown.bs.modal');}
    async hide(){if(this.closing)return;const event=await this.element.fire('hide.bs.modal');if(!event.prevented){this.closing=true;if(!this.deferHide)await this.finishHide();}return event;}
    async finishHide(){this.element.hidden=true;this.closing=false;await this.element.fire('hidden.bs.modal');}
  }
  globalThis.window={bootstrap:{Modal},addEventListener(){}};
  globalThis.location={destinations:[],replace(path){this.destinations.push(path);}};
  return document.getElementById;
}
const academy='9007199254740993';
const actor={userId:'100',academiaId:academy,perfilId:'800'};
const user=(id,nome,perfil='20',ativo=true,tenant=academy)=>({id,academia_id:tenant,perfil_id:perfil,nome,email:nome+'@example.test',ativo});
const record=(id,usuario_id)=>({id,usuario_id,criado_em:'2026-11-16 12:34:56'});
// Real wire IDs are number tokens, never JSON strings or JavaScript Numbers.
function wire(value){return '{'+Object.entries(value).map(([key,item])=>JSON.stringify(key)+':'+
  (['id','usuario_id','academia_id','perfil_id'].includes(key)?item:JSON.stringify(item))).join(',')+'}';}
const list=items=>'['+items.map(wire).join(',')+']';
let e,module,calls,accounts,records,profiles,alunos,current,putMode,getMode,metaMode,putHold,getHold;
let sequence=0;
const sourceOriginal=await readFile('public/js/alunos.js','utf8');
let source=sourceOriginal;
const mutation=process.env.TH33_MUTATION;
if(mutation==='usuario-id')source=source.replace('{ instrutor_id: candidate.id }','{ instrutor_id: candidate.usuario_id }');
if(mutation==='number')source=source.replace('option.value = candidate.id;', 'option.value = String(Number(candidate.id));');
if(mutation==='activity')source=source.replace('validUser(user) && user.ativo === true','validUser(user)');
if(mutation==='profile')source=source.replace("&& perfil?.ativo === 1 && perfil.nome === role",'');
if(mutation==='dom')source=source.replace('const candidate = id && state.candidates?.get(id);',"const candidate = id && (state.candidates?.get(id) || {id, usuario_id:'601'});")
  .replace('state.instrutores.get(id) === candidate','true');
if(mutation==='double')source=source.replace(/if \(!state\.aluno \|\| submitting \|\| state\.loading \|\| !state\.ready[\s\S]*?'Aluno'\)\) return;/,'');
if(mutation==='stale')source=source.replace('return () => responsavelGeneration === generation && responsavel === state && responsavel.aluno?.id === alunoId;', 'return () => true;');
if(mutation==='historical')source=source.replace('const account = current && state.accounts?.get(current.usuario_id);', 'const account = state.candidates?.has(state.current) && current && state.accounts?.get(current.usuario_id);');
if(mutation)assert.notEqual(source,sourceOriginal,'Mutation must change source');
async function setup(){
  e=fixture();calls=[];current=null;putMode='ok';getMode='ok';metaMode='ok';putHold=null;getHold=null;
  alunos=[record('301','201'),record('302','202')];
  records=[record('501','601'),record('502','602'),record('503','603'),record('504','604'),record('505','605'),record('506','999')];
  accounts=[user('201','Aluno A'),user('202','Aluno B'),user('601','Instrutor válido','21'),user('602','Instrutor inativo','21',false),
    user('603','Perfil inativo','22'),user('604','Perfil alterado','20'),user('605','Outro válido','21')];
  profiles=[{id:'20',nome:'Aluno',ativo:1},{id:'21',nome:'Instrutor',ativo:1},{id:'22',nome:'Antigo',ativo:0}];
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,...options});
    if(options.method==='PUT'){
      const desired=api.parseJson(options.body).instrutor_id;
      if(putHold)await putHold.promise;
      if(putMode==='transport')throw new TypeError('SQL private');
      if(putMode==='invalid')return response('{invalid');
      if(putMode==='mismatch')return response('{"instrutor_id":505}');
      if(typeof putMode==='number')return response('{"erro":"SQL private"}',putMode);
      current=desired;return response(`{"instrutor_id":${desired}}`);
    }
    if(url.endsWith('/instrutor')){
      if(getHold)return getHold.promise;
      if(getMode==='transport')throw new TypeError('SQL private');
      if(getMode==='invalid')return response('{}');
      if(typeof getMode==='number')return response('{"erro":"SQL private"}',getMode);
      return response(`{"instrutor_id":${current}}`);
    }
    if(metaMode==='transport')throw new TypeError('SQL private');
    if(url==='/api/instrutores'){
      if(typeof metaMode==='number')return response('SQL private',metaMode);
      if(metaMode==='invalid')return response('{}');
      return response(list(records));
    }
    if(url==='/api/alunos')return response(list(alunos));
    if(url.startsWith('/api/usuarios?'))return response(list(accounts));
    if(url==='/api/perfis')return response(list(profiles));
    throw Error('Unexpected endpoint '+url);
  };
  // Test-only teardown models forced session/navigation invalidation during a
  // pending request. No test exports or bypasses are shipped to the browser.
  const instrumented=source.replace("'./api.js'",JSON.stringify(apiURL))+
    '\nexport function forceTeardownForTest(){clearResponsavel();submitting=false;}';
  module=await import('data:text/javascript;base64,'+Buffer.from(instrumented).toString('base64')+'#'+sequence++);
  module.initAlunos(actor);await module.visitAlunos();
}
const action=(index=0)=>e('alunos-rows').children[index].querySelectorAll('button').find(item=>item.dataset.action==='responsavel');
const open=(index=0)=>action(index).fire('click');
const choose=async id=>{e('aluno-responsavel-select').value=id;await e('aluno-responsavel-select').fire('change');};
const submit=()=>e('aluno-responsavel-form').fire('submit');
const close=()=>window.bootstrap.Modal.getInstance(e('aluno-responsavel-modal')).hide();
const values=()=>e('aluno-responsavel-select').children.map(item=>item.value);
const writes=()=>calls.filter(item=>item.method==='PUT');
const feedback=()=>e('aluno-responsavel-feedback').textContent;
await setup();
assert.equal(calls.length,3,'TH-31 request count');
assert.equal(calls.some(item=>item.url.endsWith('/instrutor')),false,'No N+1');
assert.equal(e('alunos-rows').querySelectorAll('button').filter(item=>item.dataset.action==='responsavel').length,2);
assert.match(action().getAttribute('aria-label'),/Aluno A/);
assert.equal(e('aluno-responsavel-modal').getAttribute('aria-labelledby'),'aluno-responsavel-title');
assert.equal(e('aluno-responsavel-select').required,true);
assert.equal(e('aluno-responsavel-select').getAttribute('aria-describedby'),'aluno-responsavel-help aluno-responsavel-feedback');
assert.equal(e('aluno-responsavel-feedback').getAttribute('aria-live'),'polite');
assert(root.querySelectorAll('label').some(item=>item.getAttribute('for')==='aluno-responsavel-select'));
assert.match(e('aluno-responsavel-modal').children.find(item=>item.tagName==='div').getAttribute('class'),/modal-dialog-scrollable/);
assert.match(e('alunos-table-container').getAttribute('class'),/table-responsive/);
const opener=action();await open();
assert.equal(calls.length,7,'Four GETs per modal');
assert.deepEqual(calls.slice(3).map(item=>item.url).sort(),['/api/alunos/301/instrutor','/api/instrutores',`/api/usuarios?academia_id=${academy}`,'/api/perfis'].sort());
assert.equal(e('aluno-responsavel-aluno').textContent,'Aluno A');
assert.equal(document.activeElement.id,'aluno-responsavel-cancel');
assert.match(e('aluno-responsavel-current').textContent,/Nenhum instrutor definido/);
assert.deepEqual(values(),['','501','505'],'Only eligible registered instructors');
assert.equal(e('aluno-responsavel-submit').textContent,'Definir instrutor');
assert.equal(e('aluno-responsavel-submit').disabled,true);
await submit();assert.equal(writes().length,0);
const fake=new Element('option');fake.value='777';e('aluno-responsavel-select').append(fake);
await choose('777');await submit();assert.equal(writes().length,0,'DOM tampering must not write');
assert.match(feedback(),/instrutor válido/);
for(const value of ['', '0','-1','1e3','9223372036854775808','601']){await choose(value);await submit();assert.equal(writes().length,0);}
await choose('501');assert.equal(e('aluno-responsavel-submit').disabled,false);await submit();
assert.equal(writes().length,1);assert.equal(writes()[0].url,'/api/alunos/301/instrutor');
assert.equal(writes()[0].body,'{"instrutor_id":501}','Instrutor.id, not Usuario.id');
assert.equal(calls.length,8,'Saving adds only one PUT');assert.match(feedback(),/definido com sucesso/);
assert.match(e('aluno-responsavel-current').textContent,/Instrutor válido/);
await choose('501');await submit();assert.equal(writes().length,1,'Same instructor must not write');
await choose('505');await submit();assert.match(feedback(),/alterado com sucesso/);
assert.equal(writes().at(-1).body,'{"instrutor_id":505}');
await close();assert.equal(document.activeElement,opener);assert.equal(e('aluno-responsavel-select').children.length,0);
await open(1);assert.equal(e('aluno-responsavel-aluno').textContent,'Aluno B');assert.equal(calls.at(-4).url,'/api/alunos/302/instrutor');
await close();

// Bootstrap ignores show() during its asynchronous hide transition. Keep the
// section locked until the actual hidden event, including after late A reads.
await setup();getHold=deferred();const transitionRead=getHold;
const transitionOpener=action();const transitionOpening=open();await tick();
const transitionModal=window.bootstrap.Modal.getInstance(e('aluno-responsavel-modal'));
transitionModal.deferHide=true;const beforeTransition=calls.length;await close();
assert.equal(action(1).disabled,true,'I1: B must remain disabled until hidden');
assert.equal(e('refresh-alunos').disabled,true);
await open(1);await module.loadAlunos();await e('aluno-responsavel-refresh').fire('click');
assert.equal(calls.length,beforeTransition,'I1: no premature B or refresh GETs');
transitionRead.resolve(response('{"instrutor_id":501}'));await transitionOpening;
assert.equal(action(1).disabled,true,'Late A finalizer must not release closing lock');
assert.equal(e('aluno-responsavel-form').getAttribute('aria-busy'),'true');
await transitionModal.finishHide();getHold=null;
assert.equal(action(1).disabled,false);assert.equal(e('refresh-alunos').disabled,false);
assert.equal(e('aluno-responsavel-form').getAttribute('aria-busy'),'false');
assert.equal(e('aluno-responsavel-select').children.length,0);
assert.equal(document.activeElement,transitionOpener);
current='505';await open(1);
assert.equal(calls.length,beforeTransition+4,'I1: B loads only after hidden');
assert.equal(e('aluno-responsavel-modal').hidden,false);
assert.equal(e('aluno-responsavel-aluno').textContent,'Aluno B');
assert.match(e('aluno-responsavel-current').textContent,/Outro válido/);
assert.equal(e('aluno-responsavel-form').getAttribute('aria-busy'),'false');
transitionModal.deferHide=false;await close();assert.equal(e('refresh-alunos').disabled,false);

for(const historical of ['502','503','504','506']){
  await setup();current=historical;await open();
  assert.equal(values().includes(historical),false);assert.match(e('aluno-responsavel-history').textContent,/Indisponível para nova seleção/);
  assert.equal(e('aluno-responsavel-current').textContent.includes('Nenhum'),false);
  const historicalUser=accounts.find(user=>user.id===records.find(item=>item.id===historical).usuario_id);
  assert.equal(e('aluno-responsavel-current').textContent,historicalUser
    ? `${historicalUser.nome} — ${historicalUser.email}` : 'Dados do responsável indisponíveis.',
    'I2: resolve historical identity from all instructors, not just eligible candidates');
  assert.equal(values().includes('501'),true,'A different eligible instructor remains available');
  await choose('501');await submit();assert.match(feedback(),/alterado com sucesso/);
}
await setup();current='501';accounts.find(item=>item.id==='601').nome='<img src=x onerror="attack()">';
accounts.find(item=>item.id==='601').email='<svg onload="attack()">';accounts[0].nome='<script>attack()</script>';
await open();assert.match(e('aluno-responsavel-current').textContent,/<img/);
assert.match(e('aluno-responsavel-aluno').textContent,/<script>/);
assert.match(e('aluno-responsavel-select').textContent,/<svg/);
assert.equal(e('aluno-responsavel-modal').querySelectorAll('script, img, svg').length,0);
for(const change of ['inactive','wrong-profile','missing-profile','inactive-profile','missing-user']){
  await setup();current='501';
  if(change==='inactive')accounts[0].ativo=false;
  if(change==='wrong-profile')accounts[0].perfil_id='21';
  if(change==='missing-profile')accounts[0].perfil_id='999';
  if(change==='inactive-profile')profiles[0].ativo=0;
  if(change==='missing-user')accounts=accounts.filter(item=>item.id!=='201');
  await open();assert.match(e('aluno-responsavel-current').textContent,/Instrutor válido/);
  assert.match(e('aluno-responsavel-help').textContent,/aluno não está elegível/);
  await choose('505');await submit();assert.equal(writes().length,0);
}
await setup();accounts.find(item=>item.id==='601').academia_id='2';await open();
assert.equal(e('aluno-responsavel-submit').disabled,true);assert.equal(values().length,1);
assert.match(feedback(),/Resposta incompatível/);
await setup();records=[];await open();assert.match(e('aluno-responsavel-help').textContent,/Nenhum instrutor válido/);
await setup();profiles.find(item=>item.id==='21').ativo=0;current='501';await open();
assert.deepEqual(values(),[''],'Inactive canonical Instrutor profile must exclude all candidates');
assert.match(e('aluno-responsavel-history').textContent,/Indisponível para nova seleção/);
assert.equal(e('aluno-responsavel-current').textContent,'Instrutor válido — Instrutor válido@example.test');
await setup();accounts.find(item=>item.id==='601').perfil_id='999';await open();
assert.deepEqual(values(),['','505'],'Missing profile must exclude candidate');
for(const limit of ['1','1099511627776','9007199254740993','9223372036854775807']){
  await setup();alunos=[record(limit,'201')];records=[record(limit,'601')];await module.loadAlunos();await open();
  assert.deepEqual(values(),['',limit],'Exact int64 option value');await choose(limit);await submit();
  assert.equal(writes()[0].url,`/api/alunos/${limit}/instrutor`);assert.equal(writes()[0].body,`{"instrutor_id":${limit}}`);
  await choose(limit);await submit();assert.equal(writes().length,1);
  for(const owner of ['aluno','instrutor']){
    await setup();
    if(owner==='aluno'){accounts[0].id=limit;alunos[0].usuario_id=limit;}
    else{accounts.find(item=>item.id==='601').id=limit;records[0].usuario_id=limit;}
    await module.loadAlunos();await open();await choose('501');await submit();
    assert.equal(writes()[0].body,'{"instrutor_id":501}','Large Usuario IDs must remain join keys only');
    assert.match(e('aluno-responsavel-current').textContent,/Instrutor válido/);
  }
}
for(const status of [400,403,404,409]){
  await setup();await open();putMode=status;await choose('501');await submit();
  assert.equal(writes().length,1);assert.equal(calls.length,8);assert.equal(e('aluno-responsavel-submit').disabled,true);
  assert.equal(feedback().includes('SQL'),false);
  assert.match(feedback(),new RegExp(({400:'não está elegível',403:'não tem permissão',404:'indisponível',409:'dados mudaram'})[status]));
  putMode='ok';await e('aluno-responsavel-refresh').fire('click');await choose('501');assert.equal(e('aluno-responsavel-submit').disabled,false);
}
await setup();await open();putMode=401;await choose('501');await submit();
assert.deepEqual(location.destinations,['/login.html']);assert.equal(e('authenticated-app').hidden,true);
for(const failure of [400,401,403,404,409,500,'transport','invalid']){
  await setup();getMode=failure;await open();
  assert.equal(e('aluno-responsavel-submit').disabled,true);assert.equal(e('aluno-responsavel-current').textContent.includes('Nenhum'),false);
  if(failure===401)assert.deepEqual(location.destinations,['/login.html']);else assert.equal(feedback().includes('SQL'),false);
}
for(const failure of [403,500,'transport','invalid']){
  await setup();current='501';metaMode=failure;await open();
  assert.equal(e('aluno-responsavel-current').textContent.includes('Nenhum'),false);
  assert.equal(e('aluno-responsavel-submit').disabled,true);assert.equal(feedback().includes('SQL'),false);
}
await setup();getHold=deferred();const opening=open();await tick();
assert.match(e('aluno-responsavel-current').textContent,/Carregando responsável/);
assert.match(e('aluno-responsavel-help').textContent,/Carregando instrutores/);
assert.equal(e('aluno-responsavel-form').getAttribute('aria-busy'),'true');
getHold.resolve(response('{"instrutor_id":null}'));await opening;
assert.equal(e('aluno-responsavel-form').getAttribute('aria-busy'),'false');

await setup();await open();await choose('501');putHold=deferred();const writing=submit();await tick();
await submit();assert.equal(writes().length,1,'Double-submit guard');
assert.equal((await close()).prevented,true,'Write must prevent modal close');
assert.equal(e('aluno-responsavel-cancel').disabled,true);assert.match(feedback(),/Salvando/);
assert.match(e('aluno-responsavel-current').textContent,/Nenhum instrutor definido/,'No optimistic replacement');
await module.loadAlunos();assert.equal(calls.length,8,'List refresh cannot race the modal write');
putHold.resolve();await writing;await close();

for(const failure of [500,'transport','invalid','mismatch']){
  await setup();await open();await choose('501');putMode=failure;current='501';
  const count=calls.length;await submit();assert.equal(calls.length,count+2,'One PUT and one reconciliation GET');
  assert.equal(writes().length,1);assert.match(feedback(),/confirmado após consulta/);
  assert.match(e('aluno-responsavel-current').textContent,/Instrutor válido/);
}
await setup();await open();await choose('501');putMode='transport';current='505';await submit();
assert.match(feedback(),/diferente do solicitado/);assert.match(e('aluno-responsavel-current').textContent,/Outro válido/);
await choose('501');await submit();assert.equal(writes().length,1);
putMode='ok';await e('aluno-responsavel-refresh').fire('click');assert.equal(e('aluno-responsavel-select').value,'');
await choose('501');await submit();assert.equal(writes().length,2);
await setup();await open();await choose('501');putMode='transport';getMode=500;await submit();
assert.match(feedback(),/Não foi possível confirmar/);assert.equal(e('aluno-responsavel-reconcile').hidden,false);
await choose('505');await submit();assert.equal(writes().length,1);
const failedCount=calls.length;await e('aluno-responsavel-refresh').fire('click');assert.equal(calls.length,failedCount,'Pending result permits only reconciliation read');
getMode='ok';current='501';await e('aluno-responsavel-reconcile').fire('click');
assert.equal(calls.length,failedCount+1);assert.equal(writes().length,1);assert.match(feedback(),/confirmado após consulta/);
// Closing after failed reconciliation cannot discard the unresolved write intent.
await setup();await open();await choose('501');putMode='transport';getMode='transport';await submit();await close();
getMode=500;await open();assert.equal(e('aluno-responsavel-reconcile').hidden,false);
await choose('505');await submit();assert.equal(writes().length,1);
getMode='ok';current='501';await e('aluno-responsavel-reconcile').fire('click');assert.match(feedback(),/confirmado após consulta/);

for(const lateResponse of [response('{"instrutor_id":501}'),response('{"erro":"private"}',404)]){
  await setup();getHold=deferred();const late=getHold;const openingA=open();await tick();await close();
  getHold=null;current='505';await open(1);const before=feedback();
  late.resolve(lateResponse);await openingA;
  assert.equal(e('aluno-responsavel-aluno').textContent,'Aluno B');
  assert.match(e('aluno-responsavel-current').textContent,/Outro válido/);
  assert.equal(feedback(),before,'Stale A must not change B feedback');
}
await setup();await open();await choose('501');putMode='transport';getHold=deferred();
const reconciling=submit();await tick();assert.equal((await close()).prevented,true,'Reconciliation must prevent close');
const oldRead=getHold;module.forceTeardownForTest();getHold=null;current='505';await open(1);
putMode='ok';putHold=deferred();await choose('501');const writingB=submit();await tick();
oldRead.resolve(response('{"instrutor_id":501}'));await reconciling;
assert.equal(e('aluno-responsavel-aluno').textContent,'Aluno B');assert.match(e('aluno-responsavel-current').textContent,/Outro válido/);
assert.equal(feedback(),'Salvando...','Old reconciliation must not change B');
assert.equal(e('aluno-responsavel-form').getAttribute('aria-busy'),'true','Old finalizer must not unlock B write');
assert.equal(e('aluno-responsavel-submit').disabled,true);
putHold.resolve();await writingB;
await close();await open();assert.equal(e('aluno-responsavel-submit').disabled,true,'Old intent must reconcile before writing');
console.log(JSON.stringify({checks}));
'''


def run():
    node = shutil.which("node")
    if not node:
        candidate = Path("C:/Program Files/nodejs/node.exe")
        node = str(candidate) if candidate.exists() else None
    if not node:
        raise RuntimeError("TH-33 requires Node for JavaScript/int64 checks")
    database = ROOT / "data/traininghub.db"
    before = hashlib.sha256(database.read_bytes()).digest() if database.exists() else None
    markup = Markup()
    markup.feed((ROOT / "public/index.html").read_text(encoding="utf-8"))
    script = JS.replace("__MARKUP__", json.dumps(markup.root, ensure_ascii=True))
    env = dict(os.environ)
    env.pop("TH33_MUTATION", None)
    result = subprocess.run([node, "--input-type=module", "-"], input=script,
                            text=True, encoding="utf-8", cwd=ROOT, env=env, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    print(f"TH-33 JavaScript/DOM: {json.loads(result.stdout)['checks']} assertions passed.", flush=True)
    mutations = ["usuario-id", "number", "activity", "profile", "dom", "double", "stale", "historical"]
    for mutation in mutations:
        mutated = subprocess.run([node, "--input-type=module", "-"], input=script,
                                 text=True, encoding="utf-8", cwd=ROOT,
                                 env=env | {"TH33_MUTATION": mutation}, capture_output=True)
        assert mutated.returncode != 0 and "AssertionError" in mutated.stderr, (mutation, mutated.stdout, mutated.stderr[-3000:])
    after = hashlib.sha256(database.read_bytes()).digest() if database.exists() else None
    assert before == after, "Development database changed"
    print(f"TH-33 mutations: {len(mutations)}/{len(mutations)} rejected; source and persistent database unchanged. Browser layout proof is separate.")


if __name__ == "__main__":
    run()
