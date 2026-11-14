import 'dart:async';
import 'dart:convert';

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
  final _resume = TextEditingController(
    text: 'Год писал на Python. Прошёл учебный курс по FastAPI',
  );
  final _id = TextEditingController(text: _exampleId);
  final _client = http.Client();

  bool _loading = false;
  String? _error;
  Map<String, dynamic>? _result;

  @override
  void dispose() {
    _client.close();
    _vacancy.dispose();
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
    return Scaffold(
      appBar: AppBar(title: const Text('ИИ-Рекрутер')),
      body: Center(
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
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              if (result != null) _AnalysisResult(result: result),
            ],
          ),
        ),
      ),
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 24),
        Text(
          '${score % 1 == 0 ? score.toStringAsFixed(0) : score.toString()}%',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: (score / 100).clamp(0.0, 1.0).toDouble(),
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
        if (missing is List && missing.isNotEmpty)
          Text(
            'Не подтверждены обязательные критерии: '
            '${missing.map((id) => titles[id] ?? id).join(', ')}',
          ),
      ],
    );
  }
}
