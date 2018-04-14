import datetime
import json
import os
import re
import shutil
import subprocess
import time

debug = True
with open('defaults.json') as d,open('keycodes.json') as k:
    defaults = json.load(d)
    keycodes = json.load(k)
exe = defaults['exe']
for key,value in defaults['local'].items():
    defaults['local'][key] = os.path.expandvars(value)

#I can't lmao
exists = '''if [ -e {} ]
then
    echo "True"
else
    echo "False"
fi'''

def merge(src, dst,log = False):
    if not os.path.exists(dst):
        return False
    ok = True
    for path, dirs, files in os.walk(src):
        relPath = os.path.relpath(path, src)
        destPath = os.path.join(dst, relPath)
        if not os.path.exists(destPath):
            os.makedirs(destPath)
        for file in files:
            destFile = os.path.join(destPath, file)
            if os.path.isfile(destFile):
                if log:
                    print("Skipping existing file: " + os.path.join(relPath, file))
                ok = False
                continue
            srcFile = os.path.join(path, file)
            shutil.move(srcFile, destFile)
    for path, dirs, files in os.walk(src, False):
        if len(files) == 0 and len(dirs) == 0:
            os.rmdir(path)
    return ok

def _adb(*args,out = False):
    args = [exe] + list(args)
    if out:
        return subprocess.check_output(args,shell = False).decode().rstrip('\r\n')
    else:
        subprocess.call(args,shell = False)

def get_info():
    thing = _adb("devices","-l",out = True)
    formed = list(filter(bool,thing.split("\r\n")))[1:]
    main = {}
    for device in formed:
        categories = re.split(" +",device)
        device_dict = {
            "serial":categories[0],
            "mode":categories[1]
            }
        
        device_dict.update(dict(category.split(":") for category in categories[2:]))
        main[categories[0]] = device_dict
    return main
        
class device:

            
    def prim_device():
        while True:
            prim_device_serial = get_info()
            if len(prim_device_serial.keys()) > 0:
                return device(list(prim_device_serial.keys())[0])
            
    def __init__(self,serial=None):
        if serial:
            self.serial = serial
            self.info = get_info()[serial]
        else:
            self.serial,self.info = get_info().items()[0]
            
    def adb(self,*args,out = False):
        args = ['-s',self.serial]+ list(args)
        return _adb(*args,out = out)
    
    def sudo(self,*args,out = False):
        args = '"{}"'.format(" ".join(args))
        return self.adb("shell","su","-c",args,out = out)
    
    def exists(self,file):
        e = exists.format(file)
        res = self.sudo(e,out=True)
        return res == "True"
    
    def reboot(self,mode = None):
        if mode:
            if mode == "soft":
                pid = self.adb("shell","pidof","zygote",out = True)
                return self.sudo("kill",pid,out=True)

            else:
                self.adb("reboot",mode)
        else:
            self.adb("reboot")

    def delete(self,path):
        self.sudo("rm","-rf",path)

    def copy(self,remote,local,del_duplicate = True):
        if os.path.exists(computer):
            last = os.path.split(computer)[-1]
            real_dir = computer
            computer = os.path.join(defaults['temp'],last)
            flag = True
        self.adb("pull","-a",phone,computer)
        if flag:
            shutil.merge(computer,real_dir)
            if os.path.exists(computer) and delete_dups:
                shutil.rmtree(computer)

    def send_keycode(self,code):
        try:
            keycode = keycodes[code]
        except KeyError:
            keycode = str(code)
        self.adb("shell","input","keyevent",keycode)
                
    def move(self,remote,local,del_duplicate = True):
        self.copy(remote,local,del_duplicate = del_duplicate)
        self.delete(remote)
        
    def push(self,local,remote):
        self.adb('push',local,remote)
    
    def backup(*partitions,name = None,backupdir):

        options_dict = {
            "system": "S",
            "data": "D",
            "cache": "C",
            "recovery": "R",
            "spec_part_1": "1",
            "spec_part_2": "2",
            "spec_part_3": "3",
            "boot": "B",
            "as": "A"
        }
        options = "".join(options_dict[option] for option in partitions)

        if not name:
            name = "backup_"+datetime.datetime.today().strftime(defaults['date_format'])

        filename = os.path.join(backupdir,name)
        self.adb("shell","twrp","backup",options,name)
        phone_dir = "/data/media/0/TWRP/BACKUPS/{serial}/{name}".format(serial = self.serial,name = name)
        self.move(phone_dir,filename)

    def unlock_phone(self,pin):
        self.send_keycode('power')
        self.send_keycode('space')
        self.adb("shell","input","text",str(pin))
        self.send_keycode('enter')

    def install(self,name):
        if os.path.exists(name):
            local_name = name
            name = os.path.split(name)[-1]
            update_path = '{}/{}'.format(defaults['remote']['updates'],name)
            if not self.exists(update_path):
                self.push(local_name,defaults['remote']['updates'])

        else:
            update_path = '{}/{}'.format(defaults['remote']['updates'],name)
        self.adb("shell","twrp","install",update_path)
            
if __name__ == "__main__" and debug:
    d = device.prim_device()
