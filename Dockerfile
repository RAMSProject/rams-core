FROM ramsproject/sideboard
MAINTAINER RAMS Project "code@magfest.org"
LABEL version.rams-core ="0.1"

# install the requirements specified.
# this will be a bit slow on first run but subsequently will be cached.
COPY bower.json ./
RUN bower install --config.interactive=false --allow-root

# add our code - do this last, since it changes the most often
COPY . plugins/uber/

RUN paver install_deps
