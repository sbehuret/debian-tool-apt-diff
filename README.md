apt-diff: Compare and save APT packages in a Debian-based system
================================================================

Summary: apt-diff is a tool to compare and save listings of APT packages installed in a Debian-based system.

Installation: The main file apt-diff.py and its symlink apt-diff should be copied into /usr/local/bin. Python 3 is required.

How to use: apt-diff --help

> usage: apt-diff [-h] [-s] [-f] [-r] [{compare,save}] [target] [source]
> 
> Compare or save apt packages
>
> positional arguments:<br />
> &ensp;{compare,save}&emsp;compare two APT snapshots or save APT snapshot<br />
> &ensp;target&emsp;target APT snapshot, defaults to current directory<br />
> &ensp;source&emsp;source APT snapshot, defaults to current system
> 
> optional arguments:<br />
> &ensp;-h, --help&emsp;show this help message and exit<br />
> &ensp;-s, --summary&emsp;APT snapshot comparison summary<br />
> &ensp;-f, --filter&emsp;filter APT snapshot comparison<br />
> &ensp;-r, --reverse&emsp;reverse APT snapshot comparison
