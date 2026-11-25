// ignore_for_file: deprecated_member_use

import 'dart:async';
import 'dart:convert';
import 'dart:html' as web;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const _apiBase = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://caretaker.tailc28aa2.ts.net',
);

const _exampleId = '301f20ff-45bc-4e71-a3b3-284af2197188';

const _criteria = [
  {'id': 'c1', 'text': 'знает Python', 'required': true, 'weight': 2},
  {
    'id': 'c2',
    'text': 'разрабатывал API на FastAPI',
    'required': true,
    'weight': 2,
  },
  {'id': 'c3', 'text': 'работал с Docker', 'required': false, 'weight': 1},
];

const _statusLabels = {
  'confirmed': 'Подтверждено',
  'partial': 'Частично подтверждено',
  'unconfirmed': 'Не подтверждено',
};

void main() => runApp(
  const MaterialApp(debugShowCheckedModeBanner: false, home: RecruiterScreen()),
);

class RecruiterScreen extends StatefulWidget {
  const RecruiterScreen({super.key});

  @override
  State<RecruiterScreen> createState() => _RecruiterScreenState();
}

class _RecruiterScreenState extends State<RecruiterScreen> {
  final _vacancy = TextEditingController(
    text: 'Ищем Python-разработчика. Нужен опыт разработки API, Docker будет плюсом.',
  );
  final _name = TextEditingController();
  final _resume = TextEditingController(
    text: 'Год писал на Python. Прошёл учебный курс по FastAPI',
  );
  final _id = TextEditingController(text: _exampleId);
  final _client = http.Client();

  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _result;

  Future<List<Map<String, dynamic>>>? _history;

  @override
  void initState() {
    super.initState();
    _history = _loadHistory();
  }

  Future<List<Map<String, dynamic>>> _loadHistory() async {
    final url = Uri.parse('$_apiBase/api/demo/analyses');
    final response = await _client
        .get(url)
        .timeout(const Duration(seconds: 15));
    if (response.statusCode != 200) {
      throw const FormatException('History unavailable');
    }
    final body = jsonDecode(utf8.decode(response.bodyBytes)) as List;
    return body.cast<Map<String, dynamic>>();
  }

  @override
  void dispose() {
    _client.close();
    _vacancy.dispose();
    _name.dispose();
    _resume.dispose();
    _id.dispose();
    super.dispose();
  }

  Future<void> _request({required bool create}) async {
    final vacancy = _vacancy.text.trim();
    final resume = _resume.text.trim();
    final id = _id.text.trim();

    if (create && (vacancy.isEmpty || resume.isEmpty)) {
      setState(() => _error = 'Заполни текст вакансии и резюме.');
      return;
    }
    if (!create && id.isEmpty) {
      setState(() => _error = 'Введи ID анализа.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final endpoint = Uri.parse('$_apiBase/api/demo/analyses');
      final http.Response response;
      if (create) {
        response = await _client
            .post(
              endpoint,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'vacancy_text': vacancy,
                'resume_text': resume,
                'candidate_name': _name.text.trim(),
                'criteria': _criteria,
              }),
            )
            .timeout(const Duration(seconds: 45));
      } else {
        final url = endpoint.replace(
          pathSegments: [...endpoint.pathSegments, id],
        );
        response = await _client.get(url).timeout(const Duration(seconds: 45));
      }

      final body = utf8.decode(response.bodyBytes);
      if (response.statusCode != (create ? 201 : 200)) {
        Object? detail;
        try {
          final decoded = jsonDecode(body);
          if (decoded is Map<String, dynamic>) detail = decoded['detail'];
        } on FormatException {
          // An error response may have a non-JSON body.
        }
        throw FormatException(
          'Ошибка сервера (${response.statusCode}): '
          '${detail ?? 'подробности отсутствуют'}',
        );
      }

      final data = jsonDecode(body);
      if (data is! Map<String, dynamic> ||
          data['score_percent'] is! num ||
          data['analysis_id'] is! String ||
          data['criteria_results'] is! List) {
        throw const FormatException(
          'Сервер вернул результат в неожиданном формате.',
        );
      }

      if (!mounted) return;
      setState(() {
        _result = data;
        if (create) _history = _loadHistory();
        _id.text = data['analysis_id'] as String;
      });
    } on TimeoutException {
      if (mounted) setState(() => _error = 'Сервер не ответил за 45 секунд.');
    } on http.ClientException {
      if (mounted) {
        setState(
          () => _error = 'Не удалось связаться с сервером. Проверь Tailscale и ошибки в консоли Firefox (F12).',
        );
      }
    } on FormatException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    final wide = MediaQuery.sizeOf(context).width >= 820;
    final form = Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            TextField(
              controller: _vacancy,
              minLines: 4,
              maxLines: 8,
              decoration: const InputDecoration(
                labelText: 'Текст вакансии',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _name,
              maxLength: 120,
              decoration: const InputDecoration(
                labelText: 'Имя кандидата',
                border: OutlineInputBorder(),
                counterText: '',
              ),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                onPressed: _loading ? null : _uploadResume,
                icon: const Icon(Icons.attach_file),
                label: const Text('Загрузить PDF, DOCX или TXT'),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _resume,
              minLines: 4,
              maxLines: 8,
              decoration: const InputDecoration(
                labelText: 'Текст резюме',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Критерии контрольного примера: Python, FastAPI, Docker.',
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _loading ? null : () => _request(create: true),
              child: const Text('Анализировать'),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _id,
              readOnly: _loading,
              decoration: const InputDecoration(
                labelText: 'ID анализа',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: _loading ? null : () => _request(create: false),
              child: const Text('Открыть сохранённый анализ'),
            ),
            if (_loading) const LinearProgressIndicator(),
            if (_error case final error?)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(
                  error,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (result != null) _AnalysisResult(result: result),
          ],
        ),
      ),
    );
    return Scaffold(
      appBar: AppBar(title: const Text('ИИ-Рекрутер')),
      drawer: wide ? null : Drawer(child: _historyPanel(closeOnSelect: true)),
      body: Row(
        children: [
          if (wide) SizedBox(width: 284, child: _historyPanel()),
          if (wide) const VerticalDivider(width: 1),
          Expanded(child: form),
        ],
      ),
    );
  }

  Future<void> _uploadResume() async {
    final picker = web.FileUploadInputElement()..accept = '.pdf,.docx,.txt';
    final picked = Future.any([
      picker.onChange.first,
      picker.on['cancel'].first,
    ]);
    picker.click();
    await picked;
    final files = picker.files;
    if (!mounted || _loading || files == null || files.isEmpty) return;

    final file = files.single;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (file.size > 10 * 1024 * 1024) {
        throw const FormatException('Файл превышает 10 МБ.');
      }
      final form = web.FormData()..appendBlob('file', file, file.name);
      final request = web.HttpRequest()
        ..open('POST', '$_apiBase/api/demo/analyses/resume-text');
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
      final data = jsonDecode(request.responseText ?? '');
      if (request.status != 200 || data is! Map || data['text'] is! String) {
        final detail = data is Map ? data['detail'] : null;
        throw FormatException(
          detail is String ? detail : 'Не удалось прочитать файл.',
        );
      }
      if (mounted) setState(() => _resume.text = data['text'] as String);
    } on FormatException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _clearHistory() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Очистить историю?'),
        content: const Text(
          'Все сохранённые анализы будут удалены, и их ID перестанут открываться.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (!mounted || confirmed != true || _loading) return;
    setState(() => _loading = true);
    try {
      final response = await _client
          .delete(Uri.parse('$_apiBase/api/demo/analyses'))
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 204) throw const FormatException();
      if (!mounted) return;
      setState(() {
        _result = null;
        _error = null;
        _id.clear();
        _history = _loadHistory();
      });
    } on Exception {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось очистить историю.')),
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _historyPanel({bool closeOnSelect = false}) {
    return Builder(
      builder: (context) {
        final colors = Theme.of(context).colorScheme;
        return ColoredBox(
          color: colors.surfaceContainerLow,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 8, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        'История анализов',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ),
                    IconButton(
                      tooltip: 'Очистить историю',
                      onPressed: _loading ? null : _clearHistory,
                      icon: const Icon(Icons.delete_outline),
                    ),
                    IconButton(
                      tooltip: 'Обновить историю',
                      onPressed: () =>
                          setState(() => _history = _loadHistory()),
                      icon: const Icon(Icons.refresh),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: FutureBuilder(
                  future: _history,
                  builder: (context, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const Align(
                        alignment: Alignment.topCenter,
                        child: LinearProgressIndicator(),
                      );
                    }
                    if (snapshot.hasError) {
                      return TextButton(
                        onPressed: () =>
                            setState(() => _history = _loadHistory()),
                        child: const Text('Повторить загрузку истории'),
                      );
                    }
                    final entries = snapshot.data!;
                    if (entries.isEmpty) {
                      return const Padding(
                        padding: EdgeInsets.all(20),
                        child: Text('Сохранённых анализов пока нет.'),
                      );
                    }
                    return ListView.builder(
                      padding: const EdgeInsets.fromLTRB(8, 0, 8, 12),
                      itemCount: entries.length,
                      itemBuilder: (context, index) {
                        final entry = entries[index];
                        final id = entry['analysis_id'] as String;
                        final score = entry['score_percent'] as num;
                        final name = (entry['candidate_name'] as String?) ?? '';
                        return ListTile(
                          dense: true,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(24),
                          ),
                          leading: const Icon(Icons.history, size: 20),
                          selected: _result?['analysis_id'] == id,
                          selectedTileColor: colors.secondaryContainer,
                          title: Text(
                            name.isEmpty ? 'Без имени' : name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            'Совпадение ${score % 1 == 0 ? score.toInt() : score}%',
                          ),
                          enabled: !_loading,
                          onTap: () {
                            if (closeOnSelect) Navigator.pop(context);
                            _id.text = id;
                            _request(create: false);
                          },
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _AnalysisResult extends StatelessWidget {
  const _AnalysisResult({required this.result});

  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final score = (result['score_percent'] as num).toDouble();
    final criteria = result['criteria'];
    final titles = <Object?, Object?>{
      for (final criterion in _criteria) criterion['id']: criterion['text'],
      if (criteria is List)
        for (final criterion in criteria.whereType<Map>())
          criterion['id']: criterion['text'],
    };

    final rows = (result['criteria_results'] as List).whereType<Map>();
    final missing = result['unconfirmed_required'];
    final scoreLabel = switch (score) {
      < 40 => 'Низкое подтверждённое соответствие',
      < 70 => 'Среднее подтверждённое соответствие',
      _ => 'Высокое подтверждённое соответствие',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 24),
        Text(
          '${score % 1 == 0 ? score.toStringAsFixed(0) : score.toString()}%',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        Text(scoreLabel),
        const SizedBox(height: 8),
        DecoratedBox(
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(4),
          ),
          child: ShaderMask(
            blendMode: BlendMode.srcIn,
            shaderCallback: (bounds) => const LinearGradient(
              colors: [Color(0xFFDC2626), Color(0xFF2563EB)],
            ).createShader(bounds),
            child: LinearProgressIndicator(
              value: (score / 100).clamp(0.0, 1.0).toDouble(),
              color: Colors.white,
              backgroundColor: Colors.transparent,
              minHeight: 8,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
        ),
        const SizedBox(height: 16),
        for (final row in rows)
          Card(
            child: ListTile(
              title: Text(
                '${titles[row['criterion_id']] ?? row['criterion_id']}',
              ),
              subtitle: Text(
                [
                  _statusLabels[row['status']] ?? '${row['status']}',
                  if (row['reason'] case final String reason) reason,
                  if (row['quote'] case final String quote) '«$quote»',
                ].join('\n'),
              ),
            ),
          ),
        if (missing is List && missing.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            'Неподтверждённые обязательные критерии',
            style: Theme.of(context).textTheme.titleSmall,
          ),
          for (final criterion in missing)
            Text(
              '• ${criterion is Map ? criterion['text'] ?? criterion['id'] : titles[criterion] ?? criterion}',
            ),
        ],
      ],
    );
  }
}
