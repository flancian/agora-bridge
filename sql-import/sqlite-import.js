import { processFolder } from 'lib/files.js'

const GARDEN_DIR = process.env.GARDEN_DIR

let users = fs.readdirSync(GARDEN_DIR);
for (const user of users) {
    await processFolder(user)
}

