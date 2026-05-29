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

PostgreSQL and other backing services:

```shell
devbox services up
```

Django API (port 8000) and Vite frontend (port 3000) — start once, runs until you stop it:

```shell
npm run dev:up
```

Open http://localhost:3000/ . Logs: `npm run dev:logs`. Stop: `npm run dev:down`.

Foreground Vite only (same terminal, Ctrl+C stops it): `npm run dev` from the repo root.

### Production deploy

See [DEPLOY.md](DEPLOY.md) for Fly.io, Cloudflare Pages, media volume, and GitHub Actions secrets.

### Production catalog seed

From your **local dev** database (after you have contestants, templates, streak competitions, etc.):

```shell
cd backend
poetry run python manage.py export_dev_seed --copy-media
```

Copy `backend/seed/dev_catalog.json` and `backend/seed/media/` to the server, then on production:

```shell
poetry run python manage.py import_dev_seed --copy-media --flush-catalog
```

To bootstrap without a dev export (templates + FIFA World Cup 2026 bracket only):

```shell
poetry run python manage.py seed_catalog
```