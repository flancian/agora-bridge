"use strict";

import { execSync } from "node:child_process"
import * as parser from "./parser.js"
import fs from "fs"
import path from "node:path"
import { Sha, Subnode } from "./model.js"
const GARDEN_DIR = process.env.GARDEN_DIR

await Subnode.sync()
await Sha.sync()



/**
 * Get all directories at a given path and its subdirectories.
 * 
 * @param {string} distPath - The path to the directory.
 * @returns {string[]} - An array of directories.
 */
function deepGetDirectories(distPath) {
    // Get all files and directories at the given path.
    const filesAndDirs = fs.readdirSync(distPath);

    // Filter out only the directories.
    const directories = filesAndDirs.filter(file => {
        const fullPath = path.join(distPath, file);
        return fs.statSync(fullPath).isDirectory();
    });

    // Iterate over the directories and get their subdirectories.
    const subDirectories = directories.reduce((all, subDir) => {
        const subDirPath = path.join(distPath, subDir);
        const filesInSubDir = fs.readdirSync(subDirPath);
        const subDirPaths = filesInSubDir.map(file => path.join(subDir, file));
        return [...all, ...subDirPaths];
    }, []);

    return subDirectories;
}


/**
 * Process the files in a user's folder.
 * 
 * @param {string} user - The name of the user.
 */
export async function processFolder(user) {
    // Get the path to the user's folder
    let user_path = path.join(GARDEN_DIR, user)

    let current_sha = ""
    let last_sha = ""
    // Get the last stored SHA for the user
    let sha = await Sha.findOne({ where: { user } })
    if (sha) last_sha = sha.last_sha

    // Initialize an empty array for the files
    let files = []
    try { // try to get sha, might not be git folder i.e. streams
        // Get the SHA of the current commit
        current_sha = execSync(`git --git-dir=${user_path}/.git rev-parse @`)

    } catch (e) {
        console.log(e.message)
    }

    // If there is a last stored SHA
    if (last_sha) {

        // Get the file names that changed between the last stored SHA and the current commit
        let output = execSync(`git --git-dir=${user_path}/.git diff --name-only ${last_sha} @`).toString()
        files = output.split("\n").filter((name) => name != "")


    } else {
        // Store the current commit SHA for the user
        if (!sha) {
            await Sha.create({ user, last_sha: current_sha })

        } else {
            // Update the last stored SHA with the current commit SHA
            await Sha.update({ last_sha: current_sha }, { where: { user } })

        }


        // Get all files and directories in the user's folder recursively
        files = fs.readdirSync(user_path);
        files = files.concat(deepGetDirectories(path.join(GARDEN_DIR, user)))
    }


    // chunk file processing to save memory
    let chunkSize = 100
    let chunks = []
    let subnodes = []
    for (let i = 0; i < files.length; i += chunkSize) {
        chunks.push(files.slice(i, i + chunkSize))
    }

    for (const chunk of chunks) {
        let files = chunk
        // Process the Markdown files in the user's folder
        for (const file of files) {

            // Get the file extension
            let ext = file.split('.').pop();

            // If the file is not a Markdown file, skip it
            if (ext !== "md") continue

            // Get the title of the file
            let title = file.replace(/\.[^/.]+$/, "").split("/").pop().toLowerCase()

            try {
                // Process the file
                let subnode = await processFile(path.join(GARDEN_DIR, user, file), title, user)
                subnodes.push(subnode)
            } catch (e) {
                console.log(e.message)
            }
        }
    }
    await Subnode.bulkCreate(subnodes, { updateOnDuplicate: ["title", "user", "body", "links", "pushes"] })
}
/**
 * Process a file and insert or update subnode in the database.
 * @param {string} file - The path to the file to be processed.
 * @param {string} title - The title of the subnode.
 * @param {string} user - The user associated with the subnode.
 */
async function processFile(file, title, user) {
    /** @typedef {Object} Subnode
     * @property {string} title - The title of the subnode.
     * @property {string} user - The user associated with the subnode.
     * @property {string} body - The markdown body of the subnode.
     * @property {string} links - The links in the subnode in json format
     * @property {string} pushes - The push items in the subnode in json format
     * @property {string} updated - The date and time the subnode was updated.
    */

    // Read the content of the file and convert it to a string
    let body = fs.readFileSync(file).toString();

    // Parse the links from the file body
    let links = parseLinks(body);
    links = JSON.stringify(links);

    // Parse the pushes from the file body
    let pushes = "[]";
    if (body.includes("#push")) {
        pushes = parser.pushes(body);
        pushes = JSON.stringify(pushes);
    }


    // Get the current date and time in ISO format
    let updated = (new Date()).toISOString();



    // Create the subnode object
    /** @type {Subnode} */
    let subnode = { title, user, body, links, pushes, updated };

    // return subnode for bulk insert
    return subnode

}
/**
 * Parses links from content.
 *
 * @param {string} content - The content to parse links from.
 * @returns {Array} - An array of parsed links.
 */
function parseLinks(content) {
    // Regular expression to match links in the format [[link]]
    const regexp = /\[\[(.*?)\]\]/g;

    // Get all matches of the regular expression in the content
    let matches = Array.from(content.matchAll(regexp));

    // Extract the links from the matches
    let links = matches.map((match) => match[1]);

    return links;
}
