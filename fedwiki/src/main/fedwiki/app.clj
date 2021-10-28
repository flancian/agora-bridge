(ns fedwiki.app
  (:require
;;    [clojure.java.shell :refer (sh)]
   [clojure.data.json :as json]
   [clojure.java.io]
   [clojure.string]
   ;
   ))

(def output "/home/vera/agora/garden/vera.wiki.anagora.org")


(defn entries [pages]
  (vec (for [file pages]
         (let [page (slurp file)
               doc (json/read-str page :key-fn keyword)
               story (doc :story)
               texts (for [e story] (e :text))
               body (str (clojure.string/join "\n\n" texts) "\n")
               name (last (clojure.string/split file #"/"))]
           {:name name :body body}))))

(defn run []
  (let [pages (mapv str (filter #(.isFile %) (file-seq (clojure.java.io/file "/home/vera/.wiki/pages"))))
        entries (entries pages)]
    (vec (for [entry entries] (spit (str output "/" (entry :name) ".md") (entry :body))))))
