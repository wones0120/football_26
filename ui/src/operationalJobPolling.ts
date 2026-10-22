import {startSingleFlightPolling} from './singleFlightPolling.ts';

type Progress = {status:string;error_message?:string|null};
type PollingOptions = Omit<Parameters<typeof startSingleFlightPolling>[0], 'fetch'|'onValue'|'onError'|'intervalMs'>;

/** Share status-only waits; stop on completion, failure, or transport error. */
export function createJobCompletionWaiter<T extends Progress>(read:(id:string)=>Promise<T>, options:PollingOptions={}) {
  const pending=new Map<string,Promise<T>>();
  return (id:string):Promise<T>=>{
    const existing=pending.get(id);
    if(existing)return existing;
    const result=new Promise<T>((resolve,reject)=>{
      const controller=startSingleFlightPolling<T>({...options,fetch:()=>read(id),intervalMs:3000,
        onValue:job=>{
          if(job.status==='completed'){controller.stop();resolve(job);}
          else if(job.status==='failed'){controller.stop();reject(new Error(job.error_message||`Operational job ${id} failed`));}
        },onError:error=>{controller.stop();reject(error);}});
    });
    pending.set(id,result);
    void result.then(()=>pending.delete(id),()=>pending.delete(id));
    return result;
  };
}
