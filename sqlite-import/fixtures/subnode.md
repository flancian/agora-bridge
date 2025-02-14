- Woke up by [[Bodensee]].
  - Will miss [[Flancia meet]] today as I temporarily don't have internet connectivity.
  - Will try to catch up later with people who were/are around! Apologies for missing it.
- [[Flancia meet]] topics as I expected them
  - [[docker]]
  - [[agora recipe]] is running on [[coop cloud]], which is nice (this is what is serving link.agor.ai) but it needs some improvements:
    - It should be easier to override Agora settings from the coop cloud recipe proper, e.g. Agora name and sources. This could take place in the form of mounting agora.yaml as a config file?
    - It should be able to run one or more of the Agora bots which are part of [[agora bridge]] but currently not running for any Agora in agor.ai.
  - [[activitypub]]
    - Still unsure about whether to implement first-party support in e.g. [[agora server]], or to write a separate activitypub component (where? maybe in bridge?), or to rely on an existing implementation like the canonical golang one which seems quite mature and is geared precisely towards API usage (doesn't offer
- #push [[What is the Agora]]?
  - I've been wanting to write a special node which acts as explainer to the Agora that should be accessible to the average (?) internet browser, in the sense of a person browsing the internet.
  - Node [[agora]] was maybe originally that but it has amassed a lot of historical content which makes it harder to offer a 'curated' primer experience.
  - I've also been thinking about this as a [[WTF]] button which we could render in red up top, with the milder tooltip 'I don't understand / what is this place anyway?'
  - Surely writing this would be an interesting challenge in the first place :) The Agora is many things, at least to me, and probably to all the people already in the Agora of Flancia; and it has accreted layers (meanings) as time goes by.
- [[Jerome]] told me about [[Beaufort]] cheese yesterday.

As I sit here with my laptop (with [[vim]]) and no internet connection, I realize that I don't write here longform as much as I could. I guess the availability of the internet does make it easier for me to get distracted, which granted I see sometimes as a positive (it motivates a form of exploration), but might not be conducive to practicing the skill of writing coherently and consistently for more than a few bullet points in each journal.

The thought of writing in my blog again (meaning https://flancia.org/mine) has come up a few times recently. I'm unsure; I like the process of writing in my garden, and how everything I write in it automatically shows up in the Agora moments later (at least when I have an internet connection). So maybe what I want is to embrace this space as a blog, and just try to write longer form alongside with my mainly outline-style notes, like other Agora users already do so beautifully.

- [[todo]] maybe this weekend
  - [ ] Upload social media activity gathered by the [[agora bots]] to git repos.
    - This one has been in the back burner for a while and doesn't sound very hard.
    - It would also remove one of the main reasons to keep making full Agora backups -- which keep causing low disk space events in the Flancia servers.
    - All in all good bang-for-the-buck to start the weekend.
  - [ ] Fix hedgedoc
    - I think hedgedoc is not syncing to the Agora, the syncing process has some bugs at least -- while I'm dealing with 'git autopush' as per the above, it'd be a good time to take another look at this process and see if it can be made incrementally better.
  - [ ] Actually autopull [[etherpad]] or [[hedgedoc]] on empty nodes
    - I realized the other day this is quite simple; I tried this a few times in the past and ended up disabling autopull of the stoas because it can be disruptive (they tend to steal focus when pulled), but the disruption is really just because they are in the wrong position for empty nodes. Because empty nodes render on a separate template path, it should be straighforward to just embed the right stoa _right there_ in the 'nobody has noded this yet' message, making the stoa onboarding experience much more convenient.
  - merge PRs
    - [x] Aram's
    - [x] vera formatting
    - [ ] vera sqlite
  - [ ] update journals page
    - formatting of the page is all different/weird
  - [ ] the pull of flancia.org/mine is broken above because of the parenthesis -- how to fix that?
  - [ ] update [[patera]] to something non ancient?
    - whatever is running on [[hypatia]]?
