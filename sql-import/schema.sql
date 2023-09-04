CREATE TABLE IF NOT EXISTS "subnodes" (
        "title" TEXT,
        "user"  TEXT,
        "body"  TEXT,
        "links_to"      TEXT,
        "updated_at"    TEXT,
        UNIQUE("user","title"),
        PRIMARY KEY("title")
);
CREATE TABLE IF NOT EXISTS "shas" (
	"user"	TEXT,
	"last_sha"	TEXT,
	UNIQUE("user")
);
