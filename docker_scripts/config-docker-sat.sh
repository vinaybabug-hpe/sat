#!/bin/bash -xe

LOGDIR=/var/log/cray/sat

SATMANDIR=/usr/share/man/man8

NODE_IMAGE_KUBERNETES_REPO="https://github.com/Cray-HPE/node-image-build.git"
NODE_IMAGE_KUBERNETES_DIR="node-image-kubernetes"
NODE_IMAGE_KUBERNETES_PATH="boxes/ncn-node-images/k8s"
NODE_IMAGE_KUBERNETES_BRANCH="main"

# create logging directory
if [ ! -d "$LOGDIR" ]; then
    mkdir -p $LOGDIR
    chmod 755 $LOGDIR
fi

# temporarily install docutils needed for man page builds
pip install "$(grep docutils /sat/requirements-dev.lock.txt)"
# make man pages
cd /sat/docs/man
make
# remove docutils when done since it's not needed in final image
pip uninstall -y docutils

# install man pages
cd /sat
if [ ! -d "$SATMANDIR" ]; then
    mkdir -p $SATMANDIR
    chmod 755 $SATMANDIR
fi
cp docs/man/*.8 $SATMANDIR

# generate auto-completion script
cd /sat
if [ ! -d "/etc/bash_completion.d" ]; then
    mkdir -p /etc/bash_completion.d
    chmod 755 /etc/bash_completion.d
fi
register-python-argcomplete sat > /etc/bash_completion.d/sat-completion.bash
echo "source /etc/bash_completion.d/sat-completion.bash" >> /root/.bash_login

# install kubectl using same version used in ncn image
cd /sat
git clone $NODE_IMAGE_KUBERNETES_REPO $NODE_IMAGE_KUBERNETES_DIR
cd  $NODE_IMAGE_KUBERNETES_DIR
git checkout $NODE_IMAGE_KUBERNETES_BRANCH

source "${NODE_IMAGE_KUBERNETES_PATH}/files/resources/common/vars.sh"
if [ -z "$KUBERNETES_PULL_VERSION" ]; then
    KUBERNETES_PULL_VERSION=$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)
fi

curl -LO "https://storage.googleapis.com/kubernetes-release/release/v${KUBERNETES_PULL_VERSION#v}/bin/linux/amd64/kubectl"
chmod +x ./kubectl
mv ./kubectl /usr/bin
