require('source-map-support').install();
import * as loadFile from 'load-json-file'
import fetch from 'node-fetch';
import * as fs from 'fs'
import git from 'isomorphic-git'
import {server} from "./git-backend"
import { stripHtml } from "string-strip-html";
import * as express from 'express'
const app = express()
const portApi = 3141
const portGit = 3142
app.use(express.json())
app.put('/node', async (req,res) => {
    config = await loadFile("config.json")
    console.log(req.body)
    const dir = config.repoPath
    await fs.promises.mkdir(dir, { recursive: true })
    await git.init({ fs, dir })
    fs.writeFileSync(`${dir}/${req.body.name}.md`, req.body.content)
    await git.add({ fs, dir, filepath: '.' })
    await git.commit({ fs, dir, author: { name: "agora" }, message: `agora commit ${Date()}` })
    res.send('saved')
})
app.put('/repo', async (req,res) => {
    config = await loadFile("config.json")
    const yaml = config.repoYaml
    fs.appendFileSync(yaml, `\n- target: ${req.body.target}\n  url: ${req.body.url}\n  format: ${req.body.format}`);
    res.send('saved')

})
app.get('/', async (req,res) => {
    config = await loadFile("config.json")
    const dir = config.repoPath
    res.send('Welcome to the nascent Agora API! Available endpoints: PUT {/node, /repo}.')
})

app.listen(portApi, () => console.log("starting server"))

const URL = "https://api.twitter.com"
let config

async function init() {
    config = await loadFile("config.json")
}

async function authRequest(request: string) {
    const res = await fetch(`${URL}${request}`, { headers: { "Authorization": `Bearer ${config.bearer}` } })
    return await res.json()
}

async function getTweets({ username, agoraUser }) {
    let body = await authRequest(`/2/users/by/username/${username}`)
    const id = body.data.id
    body = await authRequest(`/2/users/${id}/tweets?tweet.fields=created_at&max_results=50`)
    const dir = `tweets/${agoraUser}`
    await fs.promises.mkdir(dir, { recursive: true })
    await git.init({ fs, dir })
    for (const tweet of body.data) {
        fs.writeFileSync(`${dir}/tweet ${tweet.created_at}.md`, tweet.text)
    }
    await git.add({ fs, dir, filepath: '.' })
    await git.commit({ fs, dir, author: { name: "agora" }, message: `agora commit ${Date()}` })
}

async function getActivities({ username, host, agoraUser }) {
    let res = await fetch(`https://${host}/users/${username}/outbox?page=true`)
    let body = await res.json()
    const dir = `activities/${agoraUser}`
    await fs.promises.mkdir(dir, { recursive: true })
    await git.init({ fs, dir })
    for (const item of body.orderedItems) {
        let activity = item.object
        if(!activity.content)
        {
            continue
        } 
        fs.writeFileSync(`${dir}/activity ${activity.published}.md`, stripHtml(activity.content).result)
    }
    await git.add({ fs, dir, filepath: '.' })
    await git.commit({ fs, dir, author: { name: "agora" }, message: `agora commit ${Date()}` })
}

async function main() {
    await init()
    for (const user of config.twitter) {
        console.log("grabbing",user)
        getTweets(user)
    }
    for (const user of config.activity) {
        console.log("grabbing",user)
        getActivities(user)
    }
}


// main()

// api on portApi, default 3141, see above.
// git repos on portGit, default 3142.
server.listen(portGit)
