import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// Execute the real component's callbacks with persistent hook state, without
// issuing unrelated cockpit network requests from useEffect.
test('memory selectors and draft survive optimizer scope changes; save uses memory context', async () => {
  const require=createRequire(import.meta.url);
  const ts=await import('typescript');
  const storageDescriptor=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  const storage=new Map<string,string>();
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value)}});
  const effects:Array<()=>void>=[];
  const state: unknown[]=[]; let cursor=0; let saved:Record<string,unknown>|null=null;
  const runtime={
    useState(initial:unknown) { const index=cursor++; if (!(index in state)) state[index]=typeof initial==='function' ? initial() : initial; return [state[index],(next:unknown)=>{state[index]=typeof next==='function' ? next(state[index]) : next;}]; },
    useEffect(callback:()=>void) {effects.push(callback);}, useMemo(callback:()=>unknown) {return callback();},
  };
  const globals=globalThis as typeof globalThis & {thoughtScopeRuntime?:typeof runtime;thoughtScopeApi?:Record<string,unknown>};
  globals.thoughtScopeRuntime=runtime;
  globals.thoughtScopeApi={createDigitalTwinBelief:async(payload:Record<string,unknown>)=>{saved=payload;return payload;},fetchDigitalTwinBeliefs:async()=>({rows:[]})};
  let code=ts.transpileModule(readFileSync(new URL('../src/DigitalTwin.tsx',import.meta.url),'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  code=code.replace(/import \{([^}]+)\} from "react";/,'const {$1}=globalThis.thoughtScopeRuntime;')
    .replace(/import \{([^;]*?)\} from "\.\/api";/,(_match,names:string)=>`const {${names}}=globalThis.thoughtScopeApi;`)
    .replace('import "./DigitalTwin.css";','')
    .replace('"./workspaceContext"',JSON.stringify(new URL('../src/workspaceContext.ts',import.meta.url).href))
    .replaceAll('"react/jsx-runtime"',JSON.stringify(pathToFileURL(require.resolve('react/jsx-runtime')).href));
  const {DigitalTwin}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  let globalChanges=0;
  let props={season:2026,week:6,slate:'THURSDAY_NIGHT',contestFormat:'showdown',optimizerObjective:'gpp',optimizerStatus:null,onProjectionRunChange:()=>{globalChanges++;},onNavigate:()=>{}};
  function render(){cursor=0;effects.length=0;return DigitalTwin(props);}
  type Element={type:unknown;props:Record<string,any>};
  function all(node:any):Element[]{if (!node || typeof node!=='object') return [];if(Array.isArray(node))return node.flatMap(all);return [node,...all(node.props?.children)];}
  function element(tree:any,predicate:(node:Element)=>boolean){const match=all(tree).find(predicate);assert.ok(match);return match;}
  let tree=render();
  element(tree,node=>node.props['aria-label']==='Memory slate').props.onChange({target:{value:'SUNDAY_MAIN'}});
  tree=render();element(tree,node=>node.props['aria-label']==='Memory format').props.onChange({target:{value:'classic'}});
  tree=render();element(tree,node=>node.type==='textarea' && node.props.rows===5).props.onChange({target:{value:'Philadelphia’s offensive line feels like a mess right now'}});
  props={...props,season:2027,week:1,slate:'MONDAY_NIGHT'};
  tree=render();
  assert.equal(element(tree,node=>node.props['aria-label']==='Memory slate').props.value,'SUNDAY_MAIN');
  assert.equal(element(tree,node=>node.props['aria-label']==='Memory season').props.value,2026);
  assert.equal(element(tree,node=>node.props['aria-label']==='Memory week').props.value,6);
  assert.equal(element(tree,node=>node.type==='textarea' && node.props.rows===5).props.value,'Philadelphia’s offensive line feels like a mess right now');
  effects[0](); // Persist only the memory draft effect; do not run cockpit fetches.
  state.length=0;
  tree=render();
  assert.equal(element(tree,node=>node.props['aria-label']==='Memory slate').props.value,'SUNDAY_MAIN');
  assert.equal(element(tree,node=>node.type==='textarea' && node.props.rows===5).props.value,'Philadelphia’s offensive line feels like a mess right now');
  await element(tree,node=>node.type==='form' && node.props.id==='thought-composer').props.onSubmit({preventDefault(){}});
  assert.ok(saved);assert.equal(saved!.season,2026);assert.equal(saved!.week,6);assert.equal(saved!.slate,'SUNDAY_MAIN');assert.equal(saved!.contest_format,'classic');
  assert.equal(globalChanges,0);
  delete globals.thoughtScopeRuntime;delete globals.thoughtScopeApi;
  if(storageDescriptor)Object.defineProperty(globalThis,'localStorage',storageDescriptor);else Reflect.deleteProperty(globalThis,'localStorage');
});
