// ignore_for_file: deprecated_member_use

import 'dart:async';
import 'dart:convert';
import 'dart:html' as web;

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'jobs_screen.dart';

const _apiBase = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://caretaker.tailc28aa2.ts.net',
);

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
  const MaterialApp(debugShowCheckedModeBanner: false, home: _SignIn()),
);

class _SignIn extends StatefulWidget {
  const _SignIn();

  @override
  State<_SignIn> createState() => _SignInState();
}

class _SignInState extends State<_SignIn> {
  final _login = TextEditingController();
  final _password = TextEditingController();
  String? _token;
  String? _role;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _login.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_busy || _login.text.trim().isEmpty || _password.text.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final response = await http
          .post(
            Uri.parse('$_apiBase/api/login'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'login': _login.text.trim(),
              'password': _password.text,
            }),
          )
          .timeout(const Duration(seconds: 15));
      if (!mounted) return;
      if (response.statusCode == 401) {
        setState(() => _error = 'Проверьте логин и пароль.');
        return;
      }
      if (response.statusCode != 200) throw const FormatException();
      final data = jsonDecode(utf8.decode(response.bodyBytes));
      if (data is! Map ||
          data['token'] is! String ||
          !['hr', 'admin'].contains(data['role'])) {
        throw const FormatException();
      }
      setState(() {
        _token = data['token'] as String;
        _role = data['role'] as String;
        _password.clear();
      });
    } on Exception {
      if (mounted)
        setState(
          () => _error = 'Не удалось войти. Проверьте подключение к серверу.',
        );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _logout() async {
    if (_busy || _token == null) return;
    setState(() => _busy = true);
    try {
      final response = await http
          .post(
            Uri.parse('$_apiBase/api/logout'),
            headers: {'Authorization': 'Bearer $_token'},
          )
          .timeout(const Duration(seconds: 10));
      if (response.statusCode != 200 && response.statusCode != 401) {
        throw const FormatException();
      }
      if (mounted)
        setState(() {
          _token = null;
          _role = null;
          _error = null;
        });
    } on Exception {
      if (mounted)
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Не удалось завершить сеанс. Повторите выход.'),
          ),
        );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_role == 'hr')
      return RecruiterScreen(token: _token!, onLogout: _logout);
    if (_role == 'admin') {
      return _AdminScreen(token: _token!, onLogout: _busy ? null : _logout);
    }
    return Scaffold(
      appBar: AppBar(title: const Text('ИИ-Рекрутер')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.all(24),
            children: [
              TextField(
                controller: _login,
                decoration: const InputDecoration(labelText: 'Логин'),
              ),
              TextField(
                controller: _password,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Пароль'),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 16),
              if (_error case final error?) Text(error),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: const Text('Войти'),
              ),
              if (_busy) const LinearProgressIndicator(),
            ],
          ),
        ),
      ),
    );
  }
}

class _AdminScreen extends StatefulWidget {
  const _AdminScreen({required this.token, required this.onLogout});

  final String token;
  final VoidCallback? onLogout;

  @override
  State<_AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<_AdminScreen> {
  final _login = TextEditingController();
  final _password = TextEditingController();
  List<Map<String, dynamic>> _users = [];
  String _role = 'hr';
  String? _error;
  bool _busy = false;

  Map<String, String> get _headers => {
    'Authorization': 'Bearer ${widget.token}',
  };

  @override
  void initState() {
    super.initState();
    _updateUsers();
  }

  @override
  void dispose() {
    _login.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _updateUsers([Future<http.Response> Function()? action]) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (action != null) {
        final response = await action().timeout(const Duration(seconds: 15));
        if (response.statusCode != 200) {
          final data = jsonDecode(utf8.decode(response.bodyBytes));
          final detail = data is Map ? data['detail'] : null;
          throw FormatException(
            detail is String ? detail : 'Проверьте введённые данные.',
          );
        }
      }
      final response = await http
          .get(Uri.parse('$_apiBase/api/users'), headers: _headers)
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 200)
        throw const FormatException('Не удалось загрузить пользователей.');
      final users = (jsonDecode(utf8.decode(response.bodyBytes)) as List)
          .cast<Map<String, dynamic>>();
      if (mounted) setState(() => _users = users);
    } on FormatException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on Exception {
      if (mounted) setState(() => _error = 'Не удалось связаться с сервером.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _create() {
    final login = _login.text.trim();
    final password = _password.text;
    if (login.isEmpty || password.trim().length < 12) {
      setState(() => _error = 'Укажите логин и пароль длиной от 12 символов.');
      return;
    }
    _password.clear();
    _updateUsers(
      () => http.post(
        Uri.parse('$_apiBase/api/users'),
        headers: {..._headers, 'Content-Type': 'application/json'},
        body: jsonEncode({'login': login, 'password': password, 'role': _role}),
      ),
    );
  }

  Future<void> _remove(Map<String, dynamic> user) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text("Удалить аккаунт ${user['login']}?"),
        content: const Text('Данные этого пользователя также будут удалены.'),
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
    if (!mounted || confirmed != true) return;
    await _updateUsers(
      () => http.delete(
        Uri.parse("$_apiBase/api/users/${user['id']}"),
        headers: _headers,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Управление пользователями'),
        actions: [
          TextButton(onPressed: widget.onLogout, child: const Text('Выйти')),
        ],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 620),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              TextField(
                controller: _login,
                maxLength: 100,
                decoration: const InputDecoration(
                  labelText: 'Логин нового пользователя',
                  counterText: '',
                ),
              ),
              TextField(
                controller: _password,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Пароль от 12 символов',
                ),
              ),
              DropdownButton<String>(
                value: _role,
                items: const [
                  DropdownMenuItem(value: 'hr', child: Text('HR')),
                  DropdownMenuItem(
                    value: 'admin',
                    child: Text('Администратор'),
                  ),
                ],
                onChanged: _busy
                    ? null
                    : (role) => setState(() => _role = role!),
              ),
              FilledButton(
                onPressed: _busy ? null : _create,
                child: const Text('Создать аккаунт'),
              ),
              if (_busy) const LinearProgressIndicator(),
              if (_error case final error?) Text(error),
              for (final user in _users)
                ListTile(
                  title: Text(user['login'] as String),
                  subtitle: Text(user['role'] == 'hr' ? 'HR' : 'Администратор'),
                  trailing: IconButton(
                    tooltip: 'Удалить аккаунт',
                    onPressed: _busy ? null : () => _remove(user),
                    icon: const Icon(Icons.delete_outline),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class RecruiterScreen extends StatefulWidget {
  const RecruiterScreen({super.key, required this.token, this.onLogout});

  final String token;
  final VoidCallback? onLogout;

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
  final _id = TextEditingController();
  final _client = http.Client();
  Map<String, String> get _auth => {'Authorization': 'Bearer ${widget.token}'};

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
    final url = Uri.parse('$_apiBase/api/hr/analyses');
    final response = await _client
        .get(url, headers: _auth)
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
      final endpoint = Uri.parse('$_apiBase/api/hr/analyses');
      final http.Response response;
      if (create) {
        response = await _client
            .post(
              endpoint,
              headers: {..._auth, 'Content-Type': 'application/json'},
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
        response = await _client
            .get(url, headers: _auth)
            .timeout(const Duration(seconds: 45));
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
      appBar: AppBar(
        title: const Text('ИИ-Рекрутер'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) =>
                    JobsScreen(apiBase: _apiBase, token: widget.token),
              ),
            ),
            child: const Text('Вакансии'),
          ),
          if (widget.onLogout != null)
            TextButton(onPressed: widget.onLogout, child: const Text('Выйти')),
        ],
      ),
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
        ..open('POST', '$_apiBase/api/hr/analyses/resume-text')
        ..setRequestHeader('Authorization', 'Bearer ${widget.token}');
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
          .delete(Uri.parse('$_apiBase/api/hr/analyses'), headers: _auth)
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
