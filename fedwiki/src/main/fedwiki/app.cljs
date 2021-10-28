(ns fedwiki.app
  (:require
   [clojure.java.shell :refer (sh)]
;;    [shadow.resource :as rc]
   ;
   ))

;; (def agora (rc/inline "/home/vera/.wiki/pages/agora"))

(defn init []
  (println "Hello World")
;;   (js/alert "alert box!")
;;   (println "wat?")
;;   (println file)
;;   (sh "ls")
  )


(defn run [] (sh "ls"))