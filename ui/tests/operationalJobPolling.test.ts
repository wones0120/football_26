import test from 'node:test';
import assert from 'node:assert/strict';
import {createJobCompletionWaiter} from '../src/operationalJobPolling.ts';
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function clock(){
 const timers=new Map<number,()=>void>();let id=0;const delays:number[]=[];
 return {timers,delays,options:{isVisible:()=>true,subscribeVisibility:()=>()=>{},now:()=>0,
  schedule:(fn:()=>void,delay:number)=>{delays.push(delay);timers.set(++id,fn);return id;},
  cancel:(key:unknown)=>{timers.delete(key as number);}}};
}
test('same-job waits share status reads and stop at completion',async()=>{
 const c=clock();let reads=0;const wait=createJobCompletionWaiter(async()=>({status:++reads===1?'running':'completed'}),c.options);
 const first=wait('job');assert.equal(wait('job'),first);await flush();assert.equal(reads,1);assert.deepEqual(c.delays,[3000]);
 const tick=[...c.timers.values()][0];c.timers.clear();tick();assert.equal((await first).status,'completed');await flush();assert.equal(reads,2);assert.equal(c.timers.size,0);
});
test('failure and transport errors stop polling and preserve errors',async()=>{
 for(const transport of [false,true]){
  const c=clock();const wait=createJobCompletionWaiter(async()=>{if(transport)throw new Error('network');return {status:'failed',error_message:'source gap'};},c.options);
  await assert.rejects(wait('job'),transport?/network/:/source gap/);await flush();assert.equal(c.timers.size,0);
 }
});
test('a hidden interface waits for visibility before reading',async()=>{
 const c=clock();let visible=false;let changed=()=>{};let reads=0;
 const wait=createJobCompletionWaiter(async()=>{reads++;return {status:'completed'};},{...c.options,isVisible:()=>visible,subscribeVisibility:fn=>{changed=fn;return ()=>{};}});
 const result=wait('job');await flush();assert.equal(reads,0);visible=true;changed();await result;assert.equal(reads,1);assert.equal(c.timers.size,0);
});
