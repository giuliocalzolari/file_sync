#!/usr/bin/env python
# If not standard should be in requirements.txt
import yaml
import time
import os
import fnmatch
import subprocess
from cli.log import LoggingApp

import schedule


from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from threading import Timer

__author__ = ['Giulio.Calzolari']


class ChangeHandler(FileSystemEventHandler):

    def __init__(self, config, ec2, log):
        self.config = config
        self.log = log
        self.ec2_auto = ec2

    def push_to_s3(self, sourcepath):
        try:
            import boto
            from boto.s3.key import Key

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

    def delete_s3(self, file_name_dest):
        try:
            import boto
            from boto.s3.key import Key

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

    def push_to_sftp(self, sourcepath):
        # Paramiko client configuration
        UseGSSAPI = True             # enable GSS-API / SSPI authentication
        DoGSSAPIKeyExchange = True
        Port = 22

        destpath = sourcepath

        try:
            import paramiko
            import StringIO

            f = open(self.current_repl["private_key"], 'r').read()

            keyfile = StringIO.StringIO(f)
            mykey = paramiko.RSAKey.from_private_key(keyfile)
            # ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect('myserver.compute-1.amazonaws.com',
                        username=self.current_repl["username"], pkey=mykey)
            sftp = ssh.open_sftp()
            if os.path.isfile(sourcepath):
                sftp.put(sourcepath, target)
            else:
                try:
                    sftp.mkdir(destpath)
                except IOError:
                    pass
                sftp.close()

            # dirlist on remote host
            # dirlist = sftp.listdir('.')
            # print("Dirlist: %s" % dirlist)

            # copy this demo onto the server
            # try:
            #     sftp.mkdir("demo_sftp_folder")
            # except IOError:
            #     print('(assuming demo_sftp_folder/ already exists)')
            # with sftp.open('demo_sftp_folder/README', 'w') as f:
            #     f.write('This was created by demo_sftp.py.\n')
            # with open('demo_sftp.py', 'r') as f:
            #     data = f.read()
            # sftp.open('demo_sftp_folder/demo_sftp.py', 'w').write(data)
            # print('created demo_sftp_folder/ on the server')
        except Exception as e:
            self.log.error('*** Caught exception: %s: %s' % (e.__class__, e))
            # print traceback.print_exc()
            pass
            # traceback.print_exc()

    def put_action(self, event):
        self.log.info("put_action " + event.src_path)
        for repl in self.config["replicator"]:
            if self.config["replicator"][repl]["status"] != "enable":
                continue

            c_url = self.config["replicator"][repl]["url"]
            self.current_repl = self.config["replicator"][repl]

            if c_url.startswith('s3://'):
                self.push_to_s3(event.src_path)

            if c_url.startswith('sftp://'):
                self.push_to_sftp(event.src_path)

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
                self.delete_s3(event.src_path)

            if c_url.startswith('sftp://'):
                self.delete_sftp(event.src_path)

    def on_created(self, event):
        self.log.debug("on_created: " + event.src_path)

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

    def job():
        print("I'm working...")

    def ec2_update_discovery(self, repl):
        self.log.info("get all instances match: " + repl["match_ec2"])
        return ["web-001.compute-1.amazonaws.com",
                "web-002.compute-1.amazonaws.com"]


# ===========================MAIN===========================#

    def main(self):
        self.log.info("Starting")
        self.log.debug("Getting Config")
        self.get_config()

        self.log.debug("directory Selected: " + self.config["basedir"])

        self.ec2_auto = {}
       
        for cmd_name in self.config["command"]:
            if self.config["command"][cmd_name]["exec"]:
                if self.config["command"][cmd_name]["status"] != "enable":
                    self.log.debug("CMD "+cmd_name+" in disabled mode")
                    continue

                interval = self.config["command"][cmd_name]["refresh"]
                schedule.every(interval).seconds.do(self.execute_cmd, self.config["command"][cmd_name]["exec"])
            else:
                self.log.warning("No command provided.")


        while 1:

            event_handler = ChangeHandler(self.config, self.ec2_auto, self.log)
            observer = Observer()
            observer.schedule(event_handler, self.config["basedir"], recursive=True)
            observer.start()
            try:
                while True:

                    for repl in self.config["replicator"]:
                        c_url = self.config["replicator"][repl]["url"]
                        if c_url.startswith('ec2://'):
                            # autodiscovery polling
                            interval = self.config["replicator"][repl]["refresh"]
                            schedule.every(interval).seconds.do(self.ec2_update_discovery, self.config["replicator"][repl])


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
    fs.add_param(
        "-d", "--detail", help="What to search for: ['datastore','vms','hostsystems','dvport','templates','resourcepool','datacentres','folders','vlans']", default=None, required=False, action="store")
    fs.add_param("-e", "--extra", help="Extra detail to add to a given mode",
                 default=None, required=False, action="store")
    fs.add_param("-c", "--config", help="Change the Configuration file to use",
                 default="./config.yaml", required=False, action="store")
    fs.run()
