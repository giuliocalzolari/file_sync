mirroring folder on different location like sftp server or s3 bucket


this is an example of config.yaml

	basedir: "/git/tool/file_sync/test_scan"
	patterns: ["*.txt","*.php"]

	command:
	 syncs3:
	  status: "disable"
	  refresh: 30   # second
	  exec: "date >> /tmp/tmp.log"
	 syncs3bis:
	  status: "disable"
	  refresh: 60   # second
	  exec: "date >> /tmp/tmp2.log"

	replicator:

	 bucket1:
	  status: "disable"
	  url: "s3://s3-eu-west-1.amazonaws.com"
	  bucket: "giulio-bk"
	  acces_key: "....."
	  secret_key: "....."
	  replace: ["/git/tool/",""] 

	 ec2web:
	  status: "enable"
	  url: "ec2://web-autodiscovery"
	  refresh: 60
	  match_ec2: "web-[0-9]+"
	  acces_key: "key123"
	  secret_key: "secter1234"
  	  mapping: "public_ip_address"  # private_ip_address , public_ip_address , public_dns_name , private_dns_name 
      region: "eu-central-1"
      private_key: "/path/.ssh/private.key"
      username: "ubuntu"
      replace: ["/Users/giuliocalzolari/git/tool/file_sync/test_scan/","/tmp/"]

	 ec2test1:
	  status: "enable"
	  url: "sftp://1.1.1.1"
	  private_key: "/path/.ssh/private.key"
	  username: "ubuntu"
	  replace: ["/git/tool/",""] 

	 ec2test2:
	  status: "enable"
	  url: "sftp://2.2.2.2"
	  password: "password"
	  username: "ubuntu"
	  replace: ["/git/tool/",""] 




