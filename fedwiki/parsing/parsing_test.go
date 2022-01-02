package parsing

import (
	"fmt"
	"testing"
)

func TestMapJson(t *testing.T) {
	host := "http://vera.wiki.anagora.org"
	url := fmt.Sprintf("%s/system/export.json", host)
	data, err := MapJson(url)
	if err != nil {
		t.Error(err)
	}
	t.Log(data)

}

func TestJsonToRecords(t *testing.T) {
	host := "http://vera.wiki.anagora.org"
	url := fmt.Sprintf("%s/system/export.json", host)
	data, err := GetJson(url)
	if err != nil {
		t.Error(err)
	}
	records := JsonToRecords(data)
	t.Log(records)
}
