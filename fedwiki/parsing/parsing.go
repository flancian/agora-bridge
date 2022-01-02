package parsing

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"strings"
	"time"

	"github.com/tidwall/gjson"
)

func MapJson(url string) (map[string]interface{}, error) {
	var data map[string]interface{}

	r, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	b, err := ioutil.ReadAll(r.Body)
	if err != nil {
		return nil, err
	}
	err = json.Unmarshal(b, &data)
	if err != nil {
		fmt.Println("error in unmarshall")
		return nil, err
	}
	return data, nil
}

func GetJson(url string) ([]byte, error) {
	r, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	b, err := ioutil.ReadAll(r.Body)
	if err != nil {
		return nil, err
	}
	return b, nil
}

// (defn json-to-pages [json]
// 	(let [body (json/read-str json :key-fn keyword)]
// 	  (for [[slug page] body]
// 		(let [content (page-to-content page)
// 			  created (page-created page)]
// 		  {:slug (name slug) :content content :created created}))))

// (defn page-to-content [page]
// 	(let [story (page :story)

// 		  texts (for [e story] (e :text))
// 		  content (str (clojure.string/join "\n\n" texts) "\n")]
// 	  content))

// (defn page-created [page]
// 	((first (filter  (fn [x] (or (= (x :type) "create") (= (x :type) "fork"))) (page :journal))) :date))

func largest(a []int64) int64 {
	max := a[0]
	for _, v := range a {
		if v > max {
			max = v
		}
	}
	return max
}

type Record struct {
	Slug    string
	Content string
	Created time.Time
}

func contentBody(page gjson.Result) string {
	texts := page.Get("story.#.text").Array()
	t := make([]string, len(texts))
	for i, v := range texts {
		t[i] = v.String()
	}
	content := strings.Join(t, "\n\n")
	return content
}

func JsonToRecords(input []byte) []Record {
	body := string(input)
	result := gjson.Parse(body)
	records := make([]Record, 0)
	result.ForEach(func(slug, page gjson.Result) bool {
		content := contentBody(page)
		vals := page.Get("journal.#.date").Array()
		ints := make([]int64, len(vals))
		for _, v := range vals {
			// ints[i] = v.Int()
			ints = append(ints, v.Int())
		}
		l := largest(ints)
		created := time.Unix(0, l*int64(time.Millisecond))
		records = append(records, Record{Slug: slug.String(), Content: content, Created: created})
		return true // keep iterating
	})

	return records

}
