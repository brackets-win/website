# Brackets.win

This repository holds the code for https://brackets.win, a website for creating bracket competitions.

## Local Development

In order to make development easier, you should install [`devbox`](https://www.jetify.com/docs/devbox), which you can install
using [these instructions](https://www.jetify.com/docs/devbox/installing-devbox).
After you have installed `devbox`, run the following commands to set up your environment for local development:

### Setup

To set up your environment after you clone the repository and install `devbox`, run the following commands:

```shell
# install all the necessary dependencies
devbox install

# initialize the local PostgreSQL database
devbox run initdb

# create a database called "brackets"
devbox run createdb brackets

# get the local database up and running so we can configure it correctly
devbox services up -b postgresql

# wait until the database is up and running, you can check this by running the following
devbox services ls

# create the local user
devbox run psql brackets -c "create user postgres with password 'password';"
devbox run psql brackets -c "grant all privileges on database brackets to postgres;"

# install any necessary depencies
devbox run install-dependencies

# run any migrations that need to be ran
devbox run migrate

# terminate the lone PostgreSQL service
devbox services stop
```

### Running the local dev environment

In order to run the dev environment locally, just the following command:

```shell
devbox services up
```