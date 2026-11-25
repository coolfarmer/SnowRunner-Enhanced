using System.Diagnostics;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using SnowRunnerEnhanced;

var program = Assembly.Load("SnowRunnerEnhanced.Setup").GetType("SnowRunnerEnhanced.Program")!;
const BindingFlags flags = BindingFlags.NonPublic | BindingFlags.Static;
var choose = program.GetMethod("ChooseGame", flags)!;
program.GetField("plain", flags)!.SetValue(null, true);
var originalInput = Console.In;
var originalOutput = Console.Out;
var fixture = Path.Combine(Path.GetTempPath(), "Enhanced-menu-été-" + Guid.NewGuid().ToString("N"));
var bin = Path.Combine(fixture, "Sources", "Bin");
Directory.CreateDirectory(bin);
File.WriteAllBytes(Path.Combine(bin, "SnowRunner.exe"), []);
int checks = 0;

void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
    checks++;
}

(string? Path, string Output) Run(string[] detected, bool autoSelect, string input)
{
    using var output = new StringWriter();
    Console.SetIn(new StringReader(input));
    Console.SetOut(output);
    try
    {
        return ((string?)choose.Invoke(null, [detected, autoSelect]), output.ToString());
    }
    catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException)
    {
        return (null, output.ToString());
    }
    finally { Console.SetIn(originalInput); Console.SetOut(originalOutput); }
}

try
{
    foreach (bool french in new[] { false, true })
    {
        program.GetField("french", flags)!.SetValue(null, french);
        var result = Run([bin], true, "");
        Check(result.Path == bin && result.Output == "", "One detected game must skip the question.");

        result = Run([], true, "2\n");
        Check(result.Path == null, "Missing game must allow Exit.");
        Check(result.Output.Contains(french ? "pas trouvé SnowRunner automatiquement" : "couldn’t find SnowRunner automatically"),
            "Missing game needs a friendly explanation.");
        Check(result.Output.Contains(Environment.NewLine + Environment.NewLine + "  2. "), "Keep a blank line before Exit.");

        result = Run([], true, "1\n\"" + fixture + "\"\n");
        Check(result.Path == bin, "Manual entry must accept a quoted game root with Unicode.");
        Check(result.Output.Contains(french ? "Parcourir les fichiers locaux" : "Browse local files"), "Show Steam folder guidance.");

        result = Run([], true, "1\n" + Path.Combine(fixture, "missing") + "\n" + bin + "\n");
        Check(result.Path == bin, "An invalid manual path must allow retry.");
        Check(result.Output.Contains(french ? "Vérifiez le chemin" : "Check the path"), "Explain how to recover from a bad path.");

        result = Run([], true, "1\n\n2\n");
        Check(result.Path == null, "Empty path must return to the menu and allow Exit.");

        result = Run([bin], false, "2\n" + fixture + "\n");
        Check(result.Path == bin && result.Output.Contains("1. " + bin), "Change folder must keep manual selection available.");

        result = Run([bin, fixture], true, "2\n");
        Check(result.Path == fixture, "Multiple installations must allow an explicit choice.");
    }
    TerminalUi.Item[] items = [new("Install", false), new("View status"), new("Customize enhancements"), new("Exit")];
    Check(TerminalUi.MoveSelection(items, 1, ConsoleKey.UpArrow) == 3, "Up must wrap and skip disabled options.");
    Check(TerminalUi.MoveSelection(items, 3, ConsoleKey.DownArrow) == 1, "Down must wrap and skip disabled options.");
    Check(TerminalUi.MoveSelection(items, 3, ConsoleKey.Home) == 1, "Home must select the first available option.");
    Check(TerminalUi.MoveSelection(items, 1, ConsoleKey.End) == 3, "End must select the final option.");
    Check(TerminalUi.MoveSelection(items, 2, ConsoleKey.A) == 2, "Unrelated keys must not change selection.");

    foreach (int width in new[] { 32, 64, 80, 120 })
    foreach (int height in new[] { 10, 24, 32 })
    {
        List<TerminalUi.Line> lines = [
            new("", Optional: true), new("SnowRunner Enhanced"),
            new(new string('─', 64)), new("Game folder".PadRight(20) + bin),
            new("", Optional: true), new("MAIN MENU"), new("", Optional: true),
            new("  Install Enhanced"), new("  View status"), new("› Customize enhancements", TerminalUi.Accent),
            new("  More options"), new("  Change language"), new(""), new("  Exit")];
        var frame = TerminalUi.RenderFrame(lines, 9, "↑ ↓ Navigate    Enter Select", width, height);
        var rows = Regex.Split(frame.Text, @"\x1b\[\d+;1H").Skip(1)
            .Select(row => Regex.Replace(row, @"\x1b\[[0-9;?]*[A-Za-z]", "")).ToArray();
        Check(rows.Length == height && rows.All(row => row.Length == width), "Every viewport cell must be painted without overflow.");
        Check(rows.Any(row => row.Contains("› Customize enhancements")), "Selected option must remain visible at every tested size.");
        Check(string.Concat(rows).Contains("Enter Select"), "Keyboard hint must remain visible at every tested size.");
        Check(frame.Text.Contains(TerminalUi.Background) && frame.Text.Contains(TerminalUi.Accent), "Reference colors must appear in every frame.");
    }
    var sanitized = TerminalUi.RenderFrame([new("Bad path \x1b]0;not-a-title\a")], 0, null, 80, 24);
    Check(!sanitized.Text.Contains("\x1b]"), "User-supplied control characters must not alter the terminal.");

    var status = JsonNode.Parse("""
        {"installed":true,"installedVersion":"0.1.0-preview.33",
         "wheelMouseEnabled":true,"skipStartupLogosEnabled":true,"mapEnabled":true,
         "generalImprovementsEnabled":true,"vehicleEnabled":true,"steeringWheelImprovementsEnabled":true,
         "files":{"SnowRunnerEnhanced.asi":"owned"},"loaderSupported":true,
         "lastRun":{"timeUtc":"2026-11-25T18:23:01.581Z","features":{
           "wheel_mouse":{"status":"active"},"skip_startup_logos":{"status":"active"},
           "map":{"status":"disabled"},"general_improvements":{"status":"active"},
           "vehicle":{"status":"active"},"steering_wheel_improvements":{"status":"active"}}}}
        """)!.AsObject();
    var localZone = TimeZoneInfo.CreateCustomTimeZone("Test local", TimeSpan.FromHours(-5), "Test local", "Test local");
    foreach (bool french in new[] { false, true })
    {
        var statusLines = StatusView.Build(status, french, timeZone: localZone);
        string text = string.Join('\n', statusLines.Select(line => line.Text));
        Check(text.Contains(french ? "CONFIGURATION" : "CONFIGURED") && text.Contains(french ? "DERNIER LANCEMENT" : "LAST LAUNCH"),
            "The table must distinguish configured choices from the last launch in both languages.");
        var featureRows = statusLines.Where(line => line.Runs != null).ToArray();
        Check(featureRows.Length == 6, "Each enhancement must have exactly one table row.");
        Check(featureRows.All(line => line.Runs![0].Color == TerminalUi.Foreground && line.Runs[0].Text.Length == 35 && line.Runs[1].Text.Length == 15),
            "Feature names must be neutral and both state columns must align.");
        Check(featureRows[2].Runs![1].Text.Trim() == (french ? "Activé" : "Enabled") && featureRows[2].Runs![2].Text == (french ? "Désactivé" : "Disabled"),
            "Map must preserve the difference between its saved choice and last recorded result.");
        Check(text.Contains(french ? "Choix modifiés" : "Choices changed") && text.Contains(french ? "prochain lancement" : "next launch"),
            "Changed choices must explain when they take effect.");
        Check(text.Contains(french ? "25 nov. 2026, 13:23" : "Nov 25, 2026, 1:23 PM") && !text.Contains("T18:23"),
            "Launch times must use the selected language and the player's local time zone.");
        Check(!text.Contains("[x]") && !text.Contains("— Enabled"), "Status rows must not look selectable or repeat the previous list.");
        var completeStatus = TerminalUi.HeaderLines();
        completeStatus.AddRange(statusLines);
        completeStatus.Add(new("", Optional: true));
        completeStatus.Add(new(french ? "› Retour" : "› Back", TerminalUi.Accent));
        var statusFrame = TerminalUi.RenderFrame(completeStatus, completeStatus.Count - 1, "", 80, 24);
        Check(statusFrame.Text.Contains("S N O W R U N N E R") && statusFrame.Text.Contains("SnowRunner Enhanced"),
            "The standard SnowRunner header must remain visible on the status screen.");
        Check(statusFrame.Text.Contains(TerminalUi.Accent + "   " + (french ? "› Retour" : "› Back")),
            "Back must be the selected menu action.");
        Check(!statusFrame.Text.Contains("Enter") && !statusFrame.Text.Contains("Entrée"), "Status must not show the old Enter Back prompt.");
        foreach (var key in new[] { ConsoleKey.UpArrow, ConsoleKey.DownArrow, ConsoleKey.Home, ConsoleKey.End })
            Check(TerminalUi.MoveSelection([new(french ? "Retour" : "Back")], 0, key) == 0,
                "Keyboard navigation must keep the sole Back action selected.");
        Check(statusFrame.Text.Contains(french ? "ÉTAT D’ENHANCED" : "VIEW STATUS") && statusFrame.Text.Contains(french ? "Améliorations du volant" : "Steering Wheel Improvements"),
            "The status title and last enhancement must fit together in a standard terminal.");
        Check(statusFrame.Text.Contains(TerminalUi.Success + (french ? "Actif" : "Active")), "Only runtime active states should receive the success color.");
        string? previewDir = Environment.GetEnvironmentVariable("ENHANCED_STATUS_PREVIEW_DIR");
        if (previewDir != null)
        {
            Directory.CreateDirectory(previewDir);
            File.WriteAllText(Path.Combine(previewDir, french ? "status-fr.ansi" : "status-en.ansi"), statusFrame.Text);
        }
        var compact = StatusView.Build(status, french, width: 34, timeZone: localZone);
        Check(compact.Count(line => line.Runs != null) == 12 && compact.Any(line => line.Text.Contains(french ? "DERNIER LANCEMENT" : "LAST LAUNCH")),
            "Narrow terminals must stack labeled states below each feature.");
        foreach (var line in compact)
        {
            var frame = TerminalUi.RenderFrame([line], 0, null, 40, 10);
            var rows = Regex.Split(frame.Text, @"\x1b\[\d+;1H").Skip(1).Select(row => Regex.Replace(row, @"\x1b\[[0-9;?]*[A-Za-z]", ""));
            Check(rows.All(row => row.Length == 40), "Colored status cells must wrap without overflowing narrow terminals.");
        }
        var missing = status.DeepClone().AsObject();
        missing.Remove("lastRun");
        var missingLines = StatusView.Build(missing, french);
        Check(missingLines.Where(line => line.Runs != null).All(line => line.Runs![2].Text == "—"), "No launch record must never imply a feature is active.");
        Check(missingLines.Any(line => line.Text.Contains(french ? "Aucun lancement" : "No recorded launch")), "Explain how to obtain missing launch information.");
        var healthy = status.DeepClone().AsObject();
        healthy["lastRun"]!["features"]!["map"]!["status"] = "active";
        Check(!StatusView.Build(healthy, french).Any(line => line.Color == TerminalUi.Warning), "Matching healthy states need no extra warning.");
        healthy["lastRun"]!["timeUtc"] = "invalid";
        healthy["lastRun"]!["features"]!["map"]!["status"] = "incompatible";
        healthy["files"]!["SnowRunnerEnhanced.asi"] = "missing";
        healthy["configurationError"] = "Missing or invalid feature configuration.";
        healthy.Remove("mapEnabled");
        var errors = StatusView.Build(healthy, french);
        Check(errors.Any(line => line.Text.Contains(french ? "Date inconnue" : "Unknown date")), "An invalid timestamp must not break the status screen.");
        Check(errors.Any(line => line.Color == TerminalUi.Error && line.Text.Contains(french ? "Fichier manquant" : "Missing file")), "File problems must remain visible.");
        Check(errors.Any(line => line.Text.Contains(french ? "Configuration absente" : "Missing or invalid configuration")), "Configuration failures must remain visible and localized.");
        foreach (var (state, expectedColor) in new[] { ("active", TerminalUi.Success), ("disabled", TerminalUi.Muted),
            ("armed", TerminalUi.Warning), ("waiting", TerminalUi.Warning), ("pending", TerminalUi.Warning),
            ("incompatible", TerminalUi.Error), ("faulted", TerminalUi.Error), ("error", TerminalUi.Error), ("unknown", TerminalUi.Muted) })
            Check(StatusView.State(state, true, french).Color == expectedColor, "Runtime states must retain their health severity.");
    }
    var coloredSanitized = TerminalUi.RenderFrame([TerminalUi.Colored(new TerminalUi.Run("Bad \x1b]0;title\a", TerminalUi.Error))], 0, null, 40, 10);
    Check(!coloredSanitized.Text.Contains("\x1b]"), "Colored status data must not inject terminal commands.");

    var frames = new List<string>();
    var elapsed = Stopwatch.StartNew();
    int operations = 0;
    TerminalUi.RunWithSpinner(() => Interlocked.Increment(ref operations), frames.Add);
    Check(operations == 1, "The spinner must execute installation exactly once.");
    Check(elapsed.Elapsed >= TimeSpan.FromSeconds(1), "A fast installation must show the spinner for at least one second.");
    Check(frames.Distinct().Count() > 1, "The spinner must animate during the minimum display time.");

    bool finished = false, animatedAfterMinimum = false;
    elapsed.Restart();
    TerminalUi.RunWithSpinner(() => { Thread.Sleep(1300); finished = true; }, _ =>
    {
        if (elapsed.Elapsed >= TimeSpan.FromSeconds(1)) animatedAfterMinimum = true;
    });
    Check(finished && animatedAfterMinimum, "A longer installation must keep animating until the operation completes.");

    var failure = new IOException("Installation test failure");
    Exception? caught = null;
    elapsed.Restart();
    try { TerminalUi.RunWithSpinner(() => throw failure, _ => { }); }
    catch (Exception error) { caught = error; }
    Check(ReferenceEquals(caught, failure), "Installation errors must reach the existing error handler without wrapping.");
    Check(elapsed.Elapsed >= TimeSpan.FromSeconds(1), "A failed installation must also respect the minimum display time.");
    Console.WriteLine($"Installer menu and rendering: {checks} checks passed.");
}
finally { Directory.Delete(fixture, recursive: true); }
