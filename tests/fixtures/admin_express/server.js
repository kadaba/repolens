const express = require('express');
const app = express();
const router = express.Router();

router.get('/admin/users', (req, res) => res.json([]));
router.post('/admin/users/grant-role', (req, res) => res.json({}));
router.post('/admin/users/revoke-permission', (req, res) => res.json({}));
router.get('/admin/audit-log', (req, res) => res.json([]));
router.get('/admin/dashboard/metrics', (req, res) => res.json({}));
router.get('/admin/dashboard/reports', (req, res) => res.json([]));

app.use('/api', router);
app.listen(3000);
