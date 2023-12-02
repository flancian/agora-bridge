# This is the project that imports a set of agora flat files and exports a sqlite database

- Firstly, make sure to `cd sqlite-import` to make this your working directory.
- Make sure to `cp .env.sample .env` and edit your paths.
  - `GARDEN_DIR` is path to your agora garden which contains user folders and files
  - `STREAM_DIR` is path to the repo containing stream data
  - `ROOT_DIR` is path to your communities agora root folder 
  - `AGORA_DB` path to your agora database sqlite output file
- Run the import with `npm run import`
