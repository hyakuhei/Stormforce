FROM ubuntu
MAINTAINER Robert Clark <hyakuhei@gmail.com>

# root user operations
# Upgrade the base and install required packages
RUN apt-get update && apt-get install -y \
  python-dev \
  libssl-dev \
  libffi-dev \
  libxml2-dev \
  libxslt1-dev \
  python-pip \
  git

# Clone Anchor, install required python packages
# Setup a user to run anchor
RUN adduser --disabled-password --gecos '' stormforce
WORKDIR /home/stormforce
RUN git clone https://github.com/hyakuhei/Stormforce.git
WORKDIR /home/stormforce/
RUN chown stormforce:stormforce *
WORKDIR /home/stormforce/Stormforce
RUN pip install -r requirements.txt

# anchor user operations
RUN su - stormforce
WORKDIR /home/stormforce
ENTRYPOINT ["/usr/bin/python","/home/stormforce/Stormforce/WaveAPI.py"]
