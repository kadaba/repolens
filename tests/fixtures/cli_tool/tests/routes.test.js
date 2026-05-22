// Test file — route extractor must NOT pick these up.
// These are fixtures for testing the analyzer, not real production routes.
const express = require('express');
const app = express();

app.get('/fake', (req, res) => res.json([]));
app.get('/also-fake', (req, res) => res.json([]));
app.get('/real', (req, res) => res.json([]));
