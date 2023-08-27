import { exec, execSync } from "node:child_process"
import fs from "fs"
import path from "node:path"
import sqlite from 'sqlite3'
import util from "util"


const GARDEN_DIR = process.env.GARDEN_DIR
const GARDEN_DB = process.env.GARDEN_DB || "./garden.db"
const DB = new sqlite.Database(GARDEN_DB);
let users = fs.readdirSync(GARDEN_DIR);
for (const user of users) {
    await processFolder(user)
}

function deepGetDirectories(distPath) {
    return fs.readdirSync(distPath).filter(function (file) {
        return fs.statSync(distPath + '/' + file).isDirectory();
    }).reduce(function (all, subDir) {
        return [...all, ...fs.readdirSync(distPath + '/' + subDir).map(e => subDir + '/' + e)]
    }, []);
}

function readAll(stmt, args) {
    console.log({ stmt })
    return new Promise((resolve, reject) => {
        DB.all(stmt, args, (err, rows) => {
            if (err) return reject(err)
            return resolve(rows)
        })
    })
}

async function processFolder(user) {
    let user_path = path.join(GARDEN_DIR, user)
    let current_sha = await readAll("select last_sha from shas where user = ? ", [user])
    console.log({ current_sha, user })
    let files = [] // init empty
    let sha = execSync(`git --git-dir=${user_path}/.git rev-parse @`)
    if (current_sha.length != 0) {
        current_sha = current_sha[0].last_sha.toString().trim()
        console.log({ current_sha })
        let output = execSync(`git --git-dir=${user_path}/.git diff --name-only ${current_sha} @`).toString()
        files = output.split("\n").filter((name) => name != "").map(name => path.join(user_path, name) != "")
        DB.run("update shas set last_sha = ? where user = ?", sha, user)
    }
    if (current_sha.length == 0) {
        DB.run("insert into shas values (?,?)", user, sha)
        files = fs.readdirSync(user_path);
        files = files.concat(deepGetDirectories(path.join(GARDEN_DIR, user)))
    }
    // throw new Error(files)
    for (const file of files) {
        let ext = file.split('.').pop();
        if (ext !== "md") continue
        let title = file.replace(/\.[^/.]+$/, "").split("/").pop().toLowerCase()
        try { await processFile(path.join(GARDEN_DIR, user, file), title, user) } catch (e) { console.log(e.message) }
    }
}
async function processFile(file, title, user) {
    console.log({ file })
    let body = fs.readFileSync(file).toString()
    let links = parseLinks(body)
    let updated = (new Date()).toISOString()
    let subnode = { title, user, body, links, updated }
    console.log(subnode)

    DB.run("insert into subnodes values (?,?,?,?,?)", [subnode.title, subnode.user, subnode.body, "[]", subnode.updated], ({ err }) => {
        if (err) {
            console.log("Error inserting subnode, trying update: ", e.message)
            DB.run("update subnodes set body = ?, links = ?, updated = ? where title = ? and user = ?", subnode.body, JSON.stringify(subnode.links), subnode.updated, subnode.title, subnode.user)

        }
    })

}

function parseLinks(content) {
    const regexp = /\[\[(.*?)\]\]/g
    let matches = content.matchAll(regexp)
    let links = Array.from(matches).map((match) => match[1])
    return links
}