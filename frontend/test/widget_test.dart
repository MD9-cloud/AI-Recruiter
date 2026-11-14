import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/main.dart' as app;

void main() {
  testWidgets('Открывается форма анализа', (tester) async {
    app.main();
    await tester.pumpAndSettle();

    expect(find.text('Анализировать'), findsOneWidget);
  });
}