from control import *
start=time.time()
result={'start_epoch':start,'topology_before':hmp('info usb')}
result['hub']=qcall('device_add',driver='usb-hub',id='astra_hub',bus='usb-bus.1',port='1.2',ports=3)
result['pad']=qcall('device_add',driver='usb-host',id='astra_pad',bus='usb-bus.1',port='1.2.1',vendorid=1118,productid=2834)
result['topology_after']=hmp('info usb')
record('attach.json',result)
for i in range(60):
    time.sleep(1)
    if (ROOT/'capture.log').stat().st_size>240*1024*1024:
        result['cap_hit']=True
        break
result['log_disable']=hmp('log none')
result['end_epoch']=time.time()
result['bytes']=(ROOT/'capture.log').stat().st_size
record('capture-result.json',result)
subprocess.run([sys.executable,str(ROOT/'control.py'),'shot','after-capture'],check=True)
print(qcall('quit'))
