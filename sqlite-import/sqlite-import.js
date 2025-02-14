import { processFolder } from "./lib/files.js";
import fs from "fs";

const GARDEN_DIR = process.env.GARDEN_DIR;
const STREAM_DIR = process.env.STREAM_DIR;
const ROOT_DIR = process.env.ROOT_DIR;

let folders = [
  { type: "garden", path: GARDEN_DIR },
  { type: "stream", path: STREAM_DIR },
  { type: "root", path: ROOT_DIR },
];

for (const folder of folders) {
  if (!folder.path) {
    continue;
  }
  let users = fs.readdirSync(folder.path);
  for (let user of users) {
    if (folder.type == "root") {
      let path = folder.path.split("/");
      user = path.pop();
      folder.path = path.join("/");
    }
    await processFolder(user, folder);
  }
}
