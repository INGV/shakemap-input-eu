# shakemap-input-eu

The scope of this project is to maintain a remote shake data repository updated, searching, at time interval,  for new shake data available on the net. 

When a file is discovered to be changed on the remote repository by external users, it is skipped.

## Quickstart
First, clone the git repositry:
```
$ git clone https://github.com/INGV/shakemap-input-eu.git
$ cd shakemap-input-eu
```

### Build docker image
```
$ docker build --no-cache --pull --build-arg ENV_UID=$(id -u) --build-arg ENV_GID=$(id -g) --tag ingv/shakemap-input-eu .
```

### Add git `remote` to `push` using `ssh`
```
$ git remote add origin_ssh git@github.com:INGV/shakemap-input-eu.git
```

### Add `ssh_key` directory into the project folder.
Create an `ssh_key` directory with valid ssh key to `push`; the ssh key must be called `id_rsa__origin_ssh` like below:
```
$ ls -l ssh_key/
total 12
-rw------- 1 shake shake 2602 Feb  7 14:26 id_rsa__origin_ssh
-rw-r--r-- 1 shake shake  571 Feb  7 14:26 id_rsa__origin_ssh.pub
$
```
after that, create a `ssh_key/config` file with this contents:
```
$ cat ssh_key/config
Host github.com
HostName github.com
PreferredAuthentications publickey
IdentityFile ~/.ssh/id_rsa__origin_ssh
```

### Run
```
$ docker run -it --rm -v $(pwd):/opt/shakemap-input-eu -v $(pwd)/ssh_key:/home/shake/.ssh ingv/shakemap-input-eu -d 1d -o /opt/shakemap-input-eu
```

## Tip
`crontab` file
```
# shakemap-input-e
*/15 * * * * (cd /home/shake/gitwork/_INGV/shakemap-input-eu && docker run --rm -v $(pwd):/opt/shakemap-input-eu -v $(pwd)/ssh_key:/home/shake/.ssh ingv/shakemap-input-eu -d 1d -o /opt/shakemap-input-eu) >> /tmp/shakemap-input-eu.log 2>&1
00 00 * * * mv /tmp/shakemap-input-eu.log /tmp/shakemap-input-eu.yesterday.log
```

## Contribute
Thanks to your contributions!

Here is a list of users who already contributed to this repository: \
<a href="https://github.com/ingv/shakemap-input-eu/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=ingv/shakemap-input-eu" />
</a>

## Author
(c) 2025 Valentino Lauciani valentino.lauciani[at]ingv.it \

Istituto Nazionale di Geofisica e Vulcanologia, Italia
