mirroring folder on different location like sftp server or s3 bucket


this is an example of config.yaml

	basedir: "/git/tool/file_sync/test_scan"
	patterns: ["*.txt","*.php"]

	command:
	 syncs3:
	  refresh: 3600   # second
	  exec: "date >> /tmp/tmp.log"
	 syncs3bis:
	  refresh: 3600   # second
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




