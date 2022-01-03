// (defn host-to-json [host] (slurp (str host "/system/export.json")))

package main

import (
	"io/ioutil"
	"os"

	"github.com/fuck-capitalism/agora-bridge/fedwiki/parsing"
)

// (doseq [page pages]
// 	(let [filename (str path "/" (page :slug) ".md")]
// 	  (spit  filename (page :content))
// 	  (let [file (java.io.File. filename)]
// 		(-> file (.setLastModified (long (page :created))))
// 		(println (str "wrote " filename)))))))

func CreateRecord(rec parsing.Record, path string) error {
	filename := path + "/" + rec.Slug + ".md"
	err := ioutil.WriteFile(filename, []byte(rec.Content), 0644)
	if err != nil {
		return err
	}
	err = os.Chtimes(filename, rec.Created, rec.Created)
	if err != nil {
		return err
	}
	return nil
}

func main() {
	url := os.Args[1] + "/system/export.json"
	path := os.Args[2]
	err := os.MkdirAll(path, os.ModePerm)
	if err != nil {
		panic(err)
	}
	json, err := parsing.GetJson(url)
	if err != nil {
		panic(err)
	}
	records := parsing.JsonToRecords(json)
	for _, rec := range records {
		err := CreateRecord(rec, path)
		if err != nil {
			panic(err)
		}
	}
}
