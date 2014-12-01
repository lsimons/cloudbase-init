* create machine from latest win2012r2 template
* install cloudbase-init msi
  * `Invoke-WebRequest -OutFile CBSetup.msi https://www.cloudbase.it/downloads/CloudbaseInitSetup_Beta_x64.msi`
  * `cmd /C "msiexec /i CBSetup.msi"`
  * check boxes to make installer run sysprep and shut down, but do *not* click finish yet
  * copy custom cloudinit/ into cloudbase-init python's site-packages
  * also copy custom cloudbaseinit/plugins/windows/{setdate.py,cloudstackpassword.py}
  * also copy custom requirements.txt
  * manually install additional requirements with pip `"C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\Python27\Scripts\pip.exe" install requests cheetah jinja2`
  * edit cloudbase-init-unattend.conf

```
[DEFAULT]
username=Administrator
groups=Administrators
inject_user_password=true
network_adapter=
config_drive_raw_hhd=true
config_drive_cdrom=true
bsdtar_path=C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\bin\bsdtar.exe
verbose=true
debug=true
logdir=C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\log\
logfile=cloudbase-init-unattend.log
default_log_levels=comtypes=INFO,suds=INFO,iso8601=WARN
logging_serial_port_settings=
mtu_use_dhcp_config=true
ntp_use_dhcp_config=true
local_scripts_path=C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\LocalScripts\
metadata_services=cloudbaseinit.metadata.services.cloudstack.CloudStack
plugins=cloudbaseinit.plugins.windows.mtu.MTUPlugin,cloudbaseinit.plugins.windows.sethostname.SetHostNamePlugin
allow_reboot=false
stop_service_on_exit=false
cloudstack_metadata_ip=10.0.1.1
```

  * edit cloudbase-init.conf

```
[DEFAULT]
username=Administrator
groups=Administrators
inject_user_password=true
network_adapter=
config_drive_raw_hhd=true
config_drive_cdrom=true
bsdtar_path=C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\bin\bsdtar.exe
verbose=true
debug=true
logdir=C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\log\
logfile=cloudbase-init.log
default_log_levels=comtypes=INFO,suds=INFO,iso8601=WARN
logging_serial_port_settings=
mtu_use_dhcp_config=true
ntp_use_dhcp_config=true
local_scripts_path=C:\Program Files (x86)\Cloudbase Solutions\Cloudbase-Init\LocalScripts\
metadata_services=cloudbaseinit.metadata.services.cloudstack.CloudStack
plugins=cloudbaseinit.plugins.windows.mtu.MTUPlugin,cloudbaseinit.plugins.windows.setdate.SetDatePlugin,cloudbaseinit.plugins.windows.sethostname.SetHostNamePlugin,cloudbaseinit.plugins.windows.networkconfig.NetworkConfigPlugin,cloudbaseinit.plugins.windows.licensing.WindowsLicensingPlugin,cloudbaseinit.plugins.windows.extendvolumes.ExtendVolumesPlugin,cloudbaseinit.plugins.windows.cloudstackpassword.SetUserPasswordPlugin,cloudbaseinit.plugins.windows.winrmlistener.ConfigWinRMListenerPlugin,cloudbaseinit.plugins.windows.winrmcertificateauth.ConfigWinRMCertificateAuthPlugin,cloudbaseinit.plugins.windows.localscripts.LocalScriptsPlugin,cloudbaseinit.plugins.windows.chef.ChefBootstrapPlugin
stop_service_on_exit=false
cloudstack_metadata_ip=10.0.1.1
set_date_url=https://betachef.example.com/chef-guard/time
chef_server_url=https://betachef.example.com/organizations/lsimons
msi_url=https://betachef.example.com/chef-guard/download?p=windows&pv=2012r2&m=x86_64&v=11.14.2-1
validation_client_name=lsimons-validator
validation_cert=-----BEGIN RSA PRIVATE KEY-----
  MII...
  .../I4wbt3x+fy5hvPVdtLLxHw=
  -----END RSA PRIVATE KEY-----
```

(Note the use of leading spaces in the validation_cert variable which is python syntax for configuration line
continuation. In this config we add two plugins `cloudbaseinit.plugins.windows.setdate.SetDatePlugin` and
`cloudbaseinit.plugins.windows.chef.ChefBootstrapPlugin`. We also specify a different metadata service
`cloudbaseinit.metadata.services.cloudstack.CloudStack`. The other new configuration options configure those new
components.)

  * stop machine in cloudstack UI
  * make template from machine

* create another machine from that template using knife cs,
  providing user-data for the new machine, as json:

```
{
	"set_date_url": "https://betachef.example.com/chef-guard/time",
	"chef_server_url": "https://betachef.example.com/organizations/lsimons",
	"validation_client_name": "lsimons-validator",
	"validation_cert": "-----BEGIN RSA...."
	"msi_url": "https://betachef.example.com/chef-guard/download?p=windows&pv=2012r2&m=x86_64&v=11.14.2-1",
	"chef_run_list": ["baseline", "chef-client"],
	"chef_environment": "Development",
}
```
