import datetime
import json
import os
import re
import shutil
import subprocess
import time

debug = True
path = os.path.dirname(__file__)
with open(os.path.join(path,'defaults.json')) as d,open(os.path.join(path,'keycodes.json')) as k:
    defaults = json.load(d)
    keycodes = json.load(k)
exe = defaults['exe']
for key,value in defaults['local'].items():
    defaults['local'][key] = os.path.expandvars(value)
    
def decode_parcel(s):
    bytes_pat = re.compile(r'(?<!0x)[a-f0-9]{8}')
    res = ''
    bytes_str = ''.join(match.group(0) for match in bytes_pat.finditer(s))
    for p in range(0,len(bytes_str),2):
        
        c= chr(int(bytes_str[p:p+2],16))
        res += c

    if '$' in res:
        res = re.search(r'(?<=\$).+',res).group(0)
        fres = ''
        for c in range(0,len(res),4):
            a = res[c:c+2]
            b = res[c+2:c+4]
            fres += b+a
        return fres
    else:
        try:
            return int(bytes_str,16)
        except:
            print(bytes_str,s)

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

#init operations
    def prim_device():
        cont = True
        while cont:
            try:
                d = device()
                cont = False
            except IndexError:
                time.sleep(1)
        return d
    #todo connect over tcip
    def __init__(self,serial=None):
        if serial:
            self.serial = serial
            info = get_info()[serial]
        else:
            serial,info = list(get_info().items())[0]
        self.__dict__.update(info)
#end of init operations

#command interface
    def adb(self,*args,out = False):
        args = ['-s',self.serial]+ list(args)
        return _adb(*args,out = out)
    def shell(self,*args,out=False):
        args = ('shell',)+args
        return self.adb(*args,out=out)
    def sudo(self,*args,out = False):
        if self.mode == 'recovery':
            return self.shell(*args,out=out)
        else:
            args = '"{}"'.format(' '.join(args).replace('"','\\"'))
            return self.shell('su','-c',args,out = out)
#end of cammand interface

#file operations
    def type(self,file):
        exists = '''if [ -e "{file}" ]; then
    if [ -d "{file}" ]; then
        echo "directory"
    elif [ -f "{file}" ]; then
        echo "file"
    else
        echo "error"
    fi
else
    echo "na"
fi'''
        e = exists.format(file = file)
        res = self.sudo(e,out=True)
        return res
    def exists(self,file):
        return self.type(file) != "na"
    def isfile(self,file):
        return self.type(file) == 'file'
    def isdir(self,file):
        return self.type(file) == 'directory'

    def delete(self,path):
        return self.sudo("rm","-rf",path,out=True)

    def copy(self,remote,local,del_duplicates = True,ignore_error=True):
        remote_type = self.type(remote)
        if remote_type != "na":
            if remote_type == "directory" and not remote.endswith('/'):
                remote += '/'
            flag = False
            if os.path.exists(local):
                last = os.path.split(local)[-1]
                real_dir = local
                local = os.path.join(defaults['local']['temp'],last)
                flag = True
            try:
                self.adb("pull","-a",remote,local,out=True)
            except subprocess.CalledProcessError as e:
                if ignore_error:
                    pass
                else:
                    raise e
            if flag:
                merge(local,real_dir)
                if os.path.exists(local) and del_duplicates:
                    shutil.rmtree(local)
        else:
            print("File not found: {}".format(remote))

    def move(self,remote,local,del_duplicates = True,ignore_error=False):
        if self.exists(remote):
            self.copy(remote,local,del_duplicates = del_duplicates,ignore_error=ignore_error)
            self.delete(remote)
        else:
            print("File not found: {}".format(remote))

    def push(self,local,remote):
        self.adb('push',local,remote)
#end of file operations

#convenience
    def reboot(self,mode = None):
        if mode:
            if mode == "soft":
                if self.mode != 'recovery':
                    pid = self.shell("pidof","zygote",out = True)
                    return self.sudo("kill",pid,out=False)
                else:
                    return self.reboot()

            else:
                self.adb("reboot",mode)
        else:
            self.adb("reboot")
        while True:
            infos = get_info()
            if len(infos) > 0:
                self.__dict__.update(get_info()[self.serial])
                break
            time.sleep(1)

    def send_keycode(self,code):
        try:
            keycode = keycodes[code]
        except KeyError:
            keycode = str(code)
        self.shell("input","keyevent",keycode)

    def unlock_phone(self,pin):
        if self.mode != 'recovery':
            if not decode_parcel(self.shell('service','call', 'power','12',out=True)):
                self.send_keycode('power')
            if decode_parcel(self.shell('service','call','trust','7',out=True)):
                self.send_keycode('space')
                self.shell("input","text",str(pin))
                self.send_keycode('enter')
#end of convenience

#twrp
    def backup(self,*partitions,name = None):
        backupdir = defaults['local']['TWRP']
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
        self.shell("twrp","backup",options,name)
        phone_dir = "/data/media/0/TWRP/BACKUPS/{serial}/{name}".format(serial = self.serial,name = name)
        self.move(phone_dir,filename)

    def wipe(self,partition):
        self.shell("twrp","wipe",partition)



    def install(self,name):
        if os.path.exists(name):
            local_name = name
            name = os.path.split(name)[-1]
            update_path = '{}/{}'.format(defaults['remote']['updates'],name)
            if not self.exists(update_path):
                self.push(local_name,defaults['remote']['updates'])

        else:
            update_path = '{}/{}'.format(defaults['remote']['updates'],name)
        self.shell("twrp","install",update_path)
#end of twrp

if __name__ == "__main__" and debug:
    d = device.prim_device()
