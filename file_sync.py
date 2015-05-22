#!/usr/bin/env python
# If not standard should be in requirements.txt
import yaml
import time
import os
import fnmatch
import subprocess
from cli.log import LoggingApp
from stat import S_ISDIR
import paramiko
import StringIO

import schedule

import boto
from boto.s3.key import Key

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from threading import Timer

__author__ = ['Giulio.Calzolari']


def mkdir_p(sftp, remote_directory):
    dir_path = str()
    for dir_folder in remote_directory.split("/"):
        if dir_folder == "":
            continue
        dir_path += r"/{0}".format(dir_folder)
        try:
            sftp.listdir(dir_path)
        except IOError:
            sftp.mkdir(dir_path)

def isdir(sftp,path):
    try:
        return S_ISDIR(sftp.stat(path).st_mode)
    except IOError:
        return False

def rm_rf(sftp, path):
    if isdir(sftp,filepath):
        rm_rf(sftp,filepath)

    files = sftp.listdir(path=path)
    # if not path.endswith("/"):
    #     path = "%s/" % path

    if not len(files):
        sftp.rmdir(path)
        return

    for f in files:
        filepath = "%s/%s" % (path, f)
        if isdir(sftp,filepath):
            rm_rf(sftp,filepath)
        else:
            sftp.remove(filepath)

class ChangeHandler(FileSystemEventHandler):

    def __init__(self, config, ec2, log):
        self.config = config
        self.log = log
        self.ec2_auto = ec2
        self.delete_queue_sftp = []

    def push_to_s3(self,event ):
        sourcepath = event.src_path
        try:

            if self.current_repl["replace"] != "":
                destpath = sourcepath.replace(
                    self.current_repl["replace"][0], self.current_repl["replace"][1])
            else:
                destpath = sourcepath

            # connect to the bucket
            conn = boto.connect_s3(
                self.current_repl["acces_key"], self.current_repl["secret_key"])
            bucket = conn.get_bucket(self.current_repl["bucket"])

            # max size in bytes before uploading in parts. between 1 and 5 GB
            # recommended
            MAX_SIZE = 20 * 1000 * 1000
            # size of parts when uploading in parts
            PART_SIZE = 6 * 1000 * 1000

            filesize = os.path.getsize(sourcepath)
            # go through each version of the file

            if filesize > MAX_SIZE:
                self.log.debug("multipart upload")
                mp = bucket.initiate_multipart_upload(destpath)
                fp = open(sourcepath, 'rb')
                fp_num = 0
                while (fp.tell() < filesize):
                    fp_num += 1
                    print "uploading part %i" % fp_num
                    mp.upload_part_from_file(
                        fp, fp_num, num_cb=10, size=PART_SIZE)

                mp.complete_upload()
            else:
                self.log.debug("singlepart upload")
                k = boto.s3.key.Key(bucket)
                k.key = destpath
                k.set_contents_from_filename(sourcepath, num_cb=10)

            k.make_public()

        except Exception as e:
            self.log.error('*** Caught exception: %s: %s' % (e.__class__, e))
            print e
            pass

    def delete_to_s3(self,event ):
        file_name_dest = event.src_path
        try:

            if self.current_repl["replace"] != "":
                file_name = file_name_dest.replace(
                    self.current_repl["replace"][0],
                    self.current_repl["replace"][1])
            else:
                file_name = file_name_dest

            self.log.debug(
                "delete: " + file_name + " from s3 bucket:"
                + self.current_repl["bucket"])

            conn = boto.connect_s3(
                self.current_repl["acces_key"],
                self.current_repl["secret_key"])
            bucket = conn.get_bucket(self.current_repl["bucket"])
            k = boto.s3.key.Key(bucket)
            k.key = file_name
            if k.exists() == True:
                key_deleted = k.delete()
                if key_deleted.exists() != False:
                    self.log.error("error on delete: " + file_name)
            else:
                self.log.warning("warning file miss: " + file_name)

        except Exception as e:
            self.log.error('*** Caught exception: %s: %s' % (e.__class__, e))
            pass


    def open_ssh(self):
        try:

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            if "private_key" in self.current_repl:
                self.log.debug("connect wit private_key to:"+self.current_repl["url"])
                f = open(self.current_repl["private_key"], 'r').read()
                mykey = paramiko.RSAKey.from_private_key(StringIO.StringIO(f))
                ssh.connect(self.current_repl["url"].replace("sftp://",""), username=self.current_repl["username"], pkey=mykey)
            elif "password" in self.current_repl:
                self.log.debug("connect wit pass to:"+self.current_repl["url"])
                ssh.connect(self.current_repl["url"].replace("sftp://",""), username=self.current_repl["username"], password=self.current_repl["password"])
            else:
                self.log.error("error invalid login credential")
                return False

            return ssh
        except Exception as e:
            self.log.error('*** Caught exception: %s: %s' % (e.__class__, e))
            # print traceback.print_exc()
            pass
            

    def push_to_sftp(self,event ):
        sourcepath = event.src_path
        # Paramiko client configuration

        if self.current_repl["replace"] != "":
            destpath = sourcepath.replace(
            self.current_repl["replace"][0], self.current_repl["replace"][1])
        else:
            destpath = sourcepath

        ssh = self.open_ssh()
        sftp = ssh.open_sftp()

        try:
            if event.is_directory:
                mkdir_p(sftp,destpath)
            else:
                sftp.put(sourcepath, destpath)    
        except Exception as e:
            mkdir_p(sftp,os.path.dirname(destpath))
            sftp.put(sourcepath, destpath)
            pass
        sftp.close()







    def delete_to_sftp(self, event ):
        sourcepath = event.src_path
        if self.current_repl["replace"] != "":
            destpath = sourcepath.replace(
            self.current_repl["replace"][0], self.current_repl["replace"][1])
            
        else:
            destpath = sourcepath


        ssh = self.open_ssh()
        sftp = ssh.open_sftp()


        try:
            if event.is_directory:
                print "rmdir "+destpath 
                sftp.rmdir(destpath)
            else:
                print "remove "+destpath 
                sftp.unlink(destpath)

            # replay deleting directory in reverse order
            for dir_queue in self.delete_queue_sftp:
                sftp.rmdir(dir_queue)

        except Exception as e:
            if event.is_directory:
                self.delete_queue_sftp.insert(0,destpath)
            else:
                self.log.error('*** Caught exception: %s: %s' % (e.__class__, e))
            pass

        
        sftp.close()

    def put_action(self, event):
        self.log.info("put_action " + event.src_path)
        for repl in self.config["replicator"]:
            if self.config["replicator"][repl]["status"] != "enable":
                continue

            c_url = self.config["replicator"][repl]["url"]
            self.current_repl = self.config["replicator"][repl]

            if c_url.startswith('s3://'):
                self.push_to_s3(event)

            if c_url.startswith('sftp://'):
                self.push_to_sftp(event)

            if c_url.startswith('ec2://'):
                print self.ec2_auto
                for ec2 in self.ec2_auto:
                    self.log.info("put_action to: " + ec2)

    def delete_action(self, event):
        self.log.info("delete_action " + event.src_path)
        for repl in self.config["replicator"]:

            if self.config["replicator"][repl]["status"] != "enable":
                continue

            c_url = self.config["replicator"][repl]["url"]
            self.current_repl = self.config["replicator"][repl]

            if c_url.startswith('s3://'):
                self.delete_to_s3(event)
            if c_url.startswith('sftp://'):
                self.delete_to_sftp(event)

    def on_created(self, event):
        self.log.debug("on_created: " + event.src_path)

        if event.is_directory:
            self.put_action(event)

        for patt in self.config["patterns"]:   
            if fnmatch.fnmatch(event.src_path, patt):
                self.put_action(event)

    def on_modified(self, event):
        self.log.debug("on_modified: " + event.src_path)

        for patt in self.config["patterns"]:
            if fnmatch.fnmatch(event.src_path, patt):
                self.put_action(event)

    def on_deleted(self, event):
        self.log.debug("on_deleted: " + event.src_path)
        if event.is_directory:
            self.delete_action(event)

        for patt in self.config["patterns"]:
            if fnmatch.fnmatch(event.src_path, patt):
                self.delete_action(event)

    def on_any_event(self, event):
        "If any file or folder is changed"

        if event.is_directory:
            self.log.debug(
                "DIR : " + event.src_path + " " + event.event_type + " ")
        else:
            self.log.debug(
                "FILE: " + event.src_path + " " + event.event_type + " ")


class FileSync(LoggingApp):

    def get_config(self):
        try:
            self.last_load = os.path.getmtime(self.params.config)
            self.config = yaml.load(open(self.params.config))
        except IOError as e:
            self.log.debug(e)
            quit("No Configuration file found at " + self.params.config)

    def execute_cmd(self, cmd):
        command_run = subprocess.call([cmd], shell=True)
        if command_run != 0:
            self.log.error("error on execute_cmd: " + cmd)
        else:
            self.log.debug("success on execute_cmd: " + cmd)

    def ec2_update_discovery(self, repl):
        self.log.info("get all instances match: " + repl["match_ec2"])
        return ["web-001.compute-1.amazonaws.com",
                "web-002.compute-1.amazonaws.com"]

    def config_scheduled_cmd(self):
        for cmd_name in self.config["command"]:
            if self.config["command"][cmd_name]["exec"]:
                if self.config["command"][cmd_name]["status"] != "enable":
                    self.log.debug("CMD "+cmd_name+" in disabled mode")
                    continue
                else:
                    self.log.debug("CMD "+cmd_name+" in enabled mode")

                interval = self.config["command"][cmd_name]["refresh"]
                schedule.every(interval).seconds.do(self.execute_cmd, self.config["command"][cmd_name]["exec"])
            else:
                self.log.warning("No command provided.")

    def ec2_autodiscovery(self):

        self.ec2_auto = {}

        for repl in self.config["replicator"]:
            c_url = self.config["replicator"][repl]["url"]
            if self.config["replicator"][repl]["status"] != "enable":
                continue
            if c_url.startswith('ec2://'):
                # autodiscovery polling
                interval = self.config["replicator"][repl]["refresh"]
                schedule.every(interval).seconds.do(self.ec2_update_discovery, self.config["replicator"][repl])



# ===========================MAIN===========================#

    def main(self):
        self.log.info("Starting")
        self.get_config()
        self.log.debug("directory Selected: " + self.config["basedir"])

        self.config_scheduled_cmd()
        self.ec2_autodiscovery()

        while 1:

            event_handler = ChangeHandler(self.config, self.ec2_auto, self.log)
            observer = Observer()
            observer.schedule(event_handler, self.config["basedir"], recursive=True)
            observer.start()
            try:
                while True:

                    if os.path.getmtime(self.params.config) != self.last_load:
                        self.log.info("Config change reloading data")
                        self.get_config()

                        schedule.clear()

                        self.config_scheduled_cmd()
                        self.ec2_autodiscovery()



                    time.sleep(1)
                    schedule.run_pending()
            except KeyboardInterrupt:
                quit("Exit")
                observer.stop()
        observer.join()

        quit("Exit")
        self.log.debug("Finished")


# ===========================MAGIC==============================#

if __name__ == "__main__":
    fs = FileSync()
    # fs.add_param("-f", "--farm", help="Which vSphere you want to connect to in your config", default=None, required=True, action="store")
    # fs.add_param("-m", "--mode", help="What to make foreman do. Excepted Values: ['index','create','command','script','snapshot','powercycle','filedrop',todo']", default=None, required=True, action="store")
    fs.add_param("-c", "--config", help="Change the Configuration file to use",
                 default="./config.yaml", required=False, action="store")
    fs.run()
