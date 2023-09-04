import { Sequelize, DataTypes } from "sequelize";
const GARDEN_DB = process.env.GARDEN_DB || "./garden.db"
const seq = new Sequelize({ dialect: "sqlite", storage: GARDEN_DB, logging: console.log });

export const Subnode = seq.define("Subnode", {
    title: {
        type: DataTypes.STRING,
    },
    user: {
        type: DataTypes.STRING,
    },
    body: {
        type: DataTypes.TEXT,
    },
    links_to: {
        type: DataTypes.TEXT,
    },
    pushes: {
        type: DataTypes.TEXT
    },
    updated_at: {
        type: DataTypes.DATE
    },

}, {
    tableName: "subnodes",

})

export const Sha = seq.define("Sha", {
    user: {
        type: DataTypes.STRING,
        unique: true
    },
    last_sha: {
        type: DataTypes.STRING
    }
}, {
    tableName: "shas"
})