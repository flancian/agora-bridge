import { expect, test } from 'vitest'
import { parse, toMarkdown, pushes } from './parser'
import fs from 'fs'
test('parses push link', () => {
    let fixture = fs.readFileSync('fixtures/subnode.md').toString()
    let results = pushes(fixture)
    console.log({ results })
    expect(results.length).toBe(1)
    expect(results[0].title).toBe("What is the Agora")
})

test('convert html to markdown', () => {
    let html = fs.readFileSync('fixtures/subnode.html').toString()
    let markdown = toMarkdown(html)
    //smoketest to ensure proper formatting, we don't need to retest library export
    console.log(markdown)
})