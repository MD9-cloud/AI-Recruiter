// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter

import 'dart:convert';
import 'dart:html' as web;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

class JobsScreen extends StatefulWidget {
  const JobsScreen({super.key, required this.apiBase, required this.token});

  final String apiBase;
  final String token;

  @override
  State<JobsScreen> createState() => _JobsScreenState();
}

class _JobsScreenState extends State<JobsScreen> {
  final _title = TextEditingController();
  final _body = TextEditingController();
  final _client = http.Client();
  List<Map<String, dynamic>> _jobs = [];
  Map<String, dynamic>? _selected;
  List<Map<String, dynamic>> _criteria = [];
  bool _dirty = false;
  String? _error;
  bool _busy = false;

  Map<String, String> get _auth => {'Authorization': 'Bearer ${widget.token}'};
  Uri _url(String path) => Uri.parse('${widget.apiBase}/api/$path');

  @override
  void initState() {
    super.initState();
    _run(_reload);
  }

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    _client.close();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on FormatException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on Exception {
      if (mounted) setState(() => _error = 'Не удалось связаться с сервером.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  dynamic _decode(int status, String body) {
    final data = jsonDecode(body);
    if (status == 200) return data;
    if (status == 401) {
      throw const FormatException('Сеанс истёк. Войдите снова.');
    }
    final detail = data is Map ? data['detail'] : null;
    throw FormatException(
      detail is String ? detail : 'Проверьте введённые данные.',
    );
  }

  Future<void> _reload() async {
    final response = await _client
        .get(_url('jobs'), headers: _auth)
        .timeout(const Duration(seconds: 15));
    final jobs = (_decode(
      response.statusCode,
      utf8.decode(response.bodyBytes),
    ) as List).cast<Map<String, dynamic>>();
    if (mounted) setState(() => _jobs = jobs);
  }

  void _select(Map<String, dynamic>? job) {
    setState(() {
      _selected = job;
      _dirty = false;
      _criteria = (job?['criteria'] as List? ?? [])
          .map((row) => Map<String, dynamic>.from(row as Map))
          .toList();
      _title.text = (job?['title'] as String?) ?? '';
      _body.text = (job?['body'] as String?) ?? '';
      _error = null;
    });
  }

  Future<void> _save() => _run(() async {
    final title = _title.text.trim();
    final body = _body.text.trim();
    if (title.isEmpty || body.isEmpty) {
      throw const FormatException('Введите название и описание вакансии.');
    }
    final selected = _selected;
    final data = jsonEncode({
      'title': title,
      'body': body,
      'criteria': _criteria,
      'sources': selected?['sources'] ?? [],
    });
    final headers = {..._auth, 'Content-Type': 'application/json'};
    final response =
        await (selected == null
                ? _client.post(_url('jobs'), headers: headers, body: data)
                : _client.put(
                    _url("jobs/${selected['id']}"),
                    headers: headers,
                    body: data,
                  ))
            .timeout(const Duration(seconds: 15));
    final result = _decode(
      response.statusCode,
      utf8.decode(response.bodyBytes),
    );
    final id = selected?['id'] ?? result['id'];
    await _reload();
    if (mounted) _select(_jobs.firstWhere((job) => job['id'] == id));
  });

  Future<void> _upload() async {
    final picker = web.FileUploadInputElement()..accept = '.pdf,.docx,.txt';
    final picked = Future.any([
      picker.onChange.first,
      picker.on['cancel'].first,
    ]);
    picker.click();
    await picked;
    final files = picker.files;
    if (!mounted || files == null || files.isEmpty) return;
    await _run(() async {
      final file = files.single;
      if (file.size > 10 * 1024 * 1024) {
        throw const FormatException('Файл превышает 10 МБ.');
      }
      final form = web.FormData()..appendBlob('file', file, file.name);
      final request = web.HttpRequest()
        ..open('POST', _url('extract').toString());
      request.setRequestHeader('Authorization', _auth['Authorization']!);
      final finished = Future.any([
        request.onLoad.first,
        request.onError.first.then(
          (_) => throw const FormatException('Сервер недоступен.'),
        ),
      ]);
      request.send(form);
      await finished.timeout(
        const Duration(seconds: 30),
        onTimeout: () {
          request.abort();
          throw const FormatException('Сервер не успел прочитать файл.');
        },
      );
      final result = _decode(request.status ?? 0, request.responseText ?? '');
      if (mounted)
        setState(() {
          _body.text = result['body'] as String;
          _dirty = true;
        });
    });
  }

  Future<void> _editCriterion([int? index]) async {
    final row = index == null ? null : _criteria[index];
    var text = row?['text'] as String? ?? '';
    var required = row?['required'] as bool? ?? true;
    var weight = row?['weight'] as int? ?? 2;
    final edited = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('Критерий вакансии'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                initialValue: text,
                maxLength: 500,
                decoration: const InputDecoration(labelText: 'Требование'),
                onChanged: (value) => update(() => text = value),
              ),
              CheckboxListTile(
                title: const Text('Обязательный'),
                value: required,
                onChanged: (value) => update(() {
                  required = value ?? false;
                  if (row == null) weight = required ? 2 : 1;
                }),
              ),
              DropdownButton<int>(
                value: weight,
                items: [
                  for (var value = 1; value <= 5; value++)
                    DropdownMenuItem(value: value, child: Text('Вес $value')),
                ],
                onChanged: (value) => update(() => weight = value!),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: text.trim().isEmpty
                  ? null
                  : () => Navigator.pop(context, {
                      'text': text.trim(),
                      'required': required,
                      'weight': weight,
                    }),
              child: const Text('Готово'),
            ),
          ],
        ),
      ),
    );
    if (!mounted || edited == null) return;
    setState(() {
      if (index == null) {
        _criteria.add(edited);
      } else {
        _criteria[index] = edited;
      }
      _dirty = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Вакансии')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 700),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              if (_busy) const LinearProgressIndicator(),
              Text(
                'Сохранённые вакансии',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              if (_jobs.isEmpty && !_busy) const Text('Вакансий пока нет.'),
              for (final job in _jobs)
                ListTile(
                  title: Text(job['title'] as String),
                  subtitle: Text("Версия ${job['version']}"),
                  selected: job['id'] == _selected?['id'],
                  onTap: _busy ? null : () => _select(job),
                ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: _busy ? null : () => _select(null),
                  icon: const Icon(Icons.add),
                  label: const Text('Новая вакансия'),
                ),
              ),
              const Divider(),
              TextField(
                controller: _title,
                onChanged: (_) => setState(() => _dirty = true),
                readOnly: _busy,
                maxLength: 200,
                decoration: const InputDecoration(
                  labelText: 'Название должности',
                ),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _busy ? null : _upload,
                  icon: const Icon(Icons.attach_file),
                  label: const Text('Загрузить PDF, DOCX или TXT'),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _body,
                onChanged: (_) => setState(() => _dirty = true),
                readOnly: _busy,
                maxLength: 30000,
                minLines: 5,
                maxLines: 12,
                decoration: const InputDecoration(
                  labelText: 'Описание вакансии',
                  border: OutlineInputBorder(),
                ),
              ),
              Text(
                'Критерии вакансии',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              for (final (index, criterion) in _criteria.indexed)
                ListTile(
                  title: Text(criterion['text'] as String),
                  subtitle: Text(
                    "${criterion['required'] == true ? 'Обязательный' : 'Желательный'}, вес ${criterion['weight']}",
                  ),
                  onTap: _busy ? null : () => _editCriterion(index),
                  trailing: IconButton(
                    tooltip: 'Удалить критерий',
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                            _criteria.removeAt(index);
                            _dirty = true;
                          }),
                    icon: const Icon(Icons.close),
                  ),
                ),
              TextButton.icon(
                onPressed: _busy || _criteria.length >= 50
                    ? null
                    : () => _editCriterion(),
                icon: const Icon(Icons.add),
                label: const Text('Добавить критерий'),
              ),
              if (_selected != null && (_dirty || _criteria.isEmpty))
                Text(
                  _criteria.isEmpty
                      ? 'Добавьте критерий для анализа.'
                      : 'Сохраните изменения перед выбором.',
                ),
              OutlinedButton(
                onPressed:
                    _busy || _dirty || _selected == null || _criteria.isEmpty
                    ? null
                    : () => Navigator.pop(context, _selected),
                child: const Text('Анализировать по этой вакансии'),
              ),
              if (_error case final error?) Text(error),
              FilledButton(
                onPressed: _busy ? null : _save,
                child: const Text('Сохранить вакансию'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
