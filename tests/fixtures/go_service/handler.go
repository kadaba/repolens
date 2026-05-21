package handler

import (
	"encoding/json"
	"net/http"
)

func Users(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode([]string{"alice", "bob"})
}
