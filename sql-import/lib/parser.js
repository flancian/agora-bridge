import $ from "jquery"
import showdown from "showdown"
import jsdom from "jsdom"
import TurndownService from "turndown"
TurndownService.prototype.escape = function (text) {
    return text
}
let turndownService = new TurndownService()
let converter = new showdown.Converter()
converter.setOption("disableForced4SpacesIndentedSublists", true)
converter.setFlavor("github")
/**
 * Parses the given markdown body and returns a jQuery object representing the parsed HTML.
 *
 * @param {string} body - The markdown body to be parsed.
 * @return {object} - The jQuery object representing the parsed HTML.
 */
export function parse(body) {
    let html = converter.makeHtml(body)
    let dom = new jsdom.JSDOM(html)
    let jq = $(dom.window)
    return jq
}

/**
 * Converts HTML to Markdown.
 *
 * @param {string} html - The HTML to be converted.
 * @return {string} The Markdown representation of the HTML.
 */
export function toMarkdown(html) {
    return turndownService.turndown(html)
}

/**
 * Retrieves a list of items from the given markdown that contain the string '#push' in the list item.
 *
 * @param {string} markdown - The markdown to parse and search through.
 * @return {Array<PushItem>} An array of objects containing the title and markdown of each list item that matches the search string.
 */
export function pushes(markdown) {
    /**
     * Represents a push item with a title and markdown content.
     *
     * @typedef {Object} PushItem
     * @property {string} title - The title of the push item.
     * @property {string} markdown - The markdown of the push item.
     */
    let jq = parse(markdown)

    /** @type {Array<PushItem>} */
    let results = jq("li:contains('#push')").toArray().map(e => {
        let regex = /\[\[(?<title>.*?)\]\]/g
        let title = regex.exec(e.outerHTML)[1]

        /** @type {PushItem} */
        let push = { title, markdown: e.outerHTML }
        return push
    })

    return results
}
