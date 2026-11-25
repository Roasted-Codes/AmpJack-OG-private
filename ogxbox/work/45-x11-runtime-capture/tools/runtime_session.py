#!/usr/bin/env python3
"""One authorized W45 cold boot -> same-client entry/load/observe/cleanup."""
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import live_adapter as a
import enum_watch as e
R=a.ROOT

def status(**kw):
    p=R/'status.json'; d=json.loads(p.read_text());d.update(kw);a.save('status.json',d)

def owned_pid(guest):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().decode().split('\0')[:-1]
            if '-config_path' in argv and argv[argv.index('-config_path')+1]==str(guest/'xemu.toml'):
                if (p/'exe').resolve().name=='xemu':found.append(int(p.name))
        except OSError:pass
    e.need(len(found)<=1,'multiple native guest writers')
    return found[0] if found else None

def run_session(fx, *, existing=False):
    """Production state machine; fixture substitutes ONLY external effects.

    Cleanup owns every boundary, including claim/command failure, discovery,
    endpoint authentication and a partially constructed second client.
    """
    q=None; r=None; ident=None; authenticated=False; transferred=False
    result=dict(command=False,new_boot=False,attach_existing=existing,native=False,title=False,module=False,healthy=False,
                clients_closed=False,physical_input='untested',first_failed_link=None)
    phase='stopped_gates_and_claim'
    try:
        if existing:
            phase='existing_binding';handle,ident=fx.existing()
        else:
            handle=fx.launch(); result['command']=True;result['new_boot']=True
            phase='native_discovery'; ident=fx.discover(handle)
        if ident is None:raise RuntimeError('native exited before discovery')
        result['native']=True
        phase='endpoint_authentication';fx.authenticate(ident,handle)
        q=fx.open_q();authenticated=True
        phase='guarded_native_parity';fx.parity(ident,handle)
        phase='rsp_open';r=fx.open_r(q,ident)
        phase='generic_load_hold';fx.load_title(q,r,ident)
        result['title']=True
        phase='install_and_topology';fx.install(q,r,ident)
        result['module']=True
        phase='ordered_observation';observed=fx.observe(q,r,ident)
        result['observer']=observed
        if observed['hold']:raise RuntimeError('decoded fault/unknown safety hold')
        phase='responsive_capture';offer=fx.capture(q,r,ident,handle)
        result['capture_ready']=True
        phase='parent_takeover';accept=fx.accept(offer)
        if accept is not None:
            validate_takeover(offer,accept)
            # Finalize durable recorder checkpoint while still the sole writer.
            fx.seal(offer)
            r.close();r=None
            a.close_q(q);q=None
            result['clients_closed']=True
            fx.release(offer)
            # Parent may acquire ONLY after release. It must demonstrate the
            # same boot, next capture sequence and its own sole-client ownership.
            fx.confirm(offer)
            transferred=True;result['takeover']=offer;result['healthy']=True
        else:result['takeover']='refused; authenticated graceful cleanup'
    except BaseException as error:
        result.update(first_failed_link=phase,error=str(error),traceback=traceback.format_exc())
        if r is not None:
            try:fx.context(r)
            except Exception as context_error:result['context_error']=str(context_error)
    finally:
        if not transferred and q is None and hasattr(fx,'cleanup_if_unopened'):
            try:result['early_authenticated_cleanup']=fx.cleanup_if_unopened()
            except Exception as error:result['early_cleanup_error']=str(error)
        if not transferred and authenticated and q is not None:
            try:
                fx.reauthenticate(ident)
                q.cmd('quit')  # never reset, force-kill, detach or resume
            except Exception as error:result['quit_error']=str(error)
        if r is not None:
            try:r.close()
            except Exception as error:result['rsp_close_error']=str(error)
        if q is not None:
            try:a.close_q(q)
            except Exception as error:result['qmp_close_error']=str(error)
        if not transferred:
            try:result['remaining_resources']=fx.verify_release()
            except Exception as error:result['release_error']=str(error)
        result['clients_closed']=not any(k in result for k in ('rsp_close_error','qmp_close_error'))
        fx.record(result)
    return result

def validate_takeover(offer,accept):
    e.need(accept.get('offer_sha256')==e.sha(json.dumps(offer,sort_keys=True).encode()),'takeover offer mismatch')
    e.need(accept.get('identity')==offer['identity'],'takeover boot/PID/start/base mismatch')
    for k in ('unit','invocation_id','qmp','gdb_port','running','capture','cleanup_owner'):
        e.need(accept.get(k)==offer[k],'takeover mismatch '+k)
    e.need(accept.get('accepted') is True and accept.get('exclusive') is True,'parent did not accept exclusive cleanup duty')

def main():
    if sys.argv[1:]==['--attach-existing']:
        from recovery import RecoveryEffects
        result=run_session(RecoveryEffects(),existing=True)
        return 0 if result.get('healthy') or result.get('remaining_resources',{}).get('released') else 1
    if sys.argv[1:]:raise ValueError('unsupported session mode')
    from recovery import FreshEffects
    result=run_session(FreshEffects())
    return 0 if result.get('healthy') and not result.get('first_failed_link') else 1

if __name__=='__main__':raise SystemExit(main())
