(ns fedwiki.app
  (:require
   [clojure.data.json :as json]
   [clojure.java.io]
   [clojure.string]
   [clojure.edn]
   ;
   ))


(defn host-to-json [host] (slurp (str host "/system/export.json")))

(defn mkdir [garden-path]
  (let [path (str garden-path)]
    (.mkdir (java.io.File. path))
    path))

(defn page-to-content [page]
  (let [story (page :story)

        texts (for [e story] (e :text))
        content (str (clojure.string/join "\n\n" texts) "\n")]
    content))
(defn page-created [page]
  ((first (filter  (fn [x] (or (= (x :type) "create") (= (x :type) "fork"))) (page :journal))) :date))

(defn json-to-pages [json]
  (let [body (json/read-str json :key-fn keyword)]
    (for [[slug page] body]
      (let [content (page-to-content page)
            created (page-created page)]
        {:slug (name slug) :content content :created created}))))

(defn run [host garden-path]

  (let [json (host-to-json host)
        pages (json-to-pages json)
        path (mkdir garden-path)]
    (doseq [page pages]
      (let [filename (str path "/" (page :slug) ".md")]
        (spit  filename (page :content))
        (let [file (java.io.File. filename)]
          (-> file (.setLastModified (long (page :created))))
          (println (str "wrote " filename)))))))
