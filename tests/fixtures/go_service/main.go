package main

import (
	"net/http"

	"github.com/example/svc/handler"
)

func main() {
	http.HandleFunc("/users", handler.Users)
	http.ListenAndServe(":8080", nil)
}
