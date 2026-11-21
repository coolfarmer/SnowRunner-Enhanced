using System.Reflection;
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
    TerminalUi.Item[] items = [new("Install", false), new("View status"), new("Choose fixes"), new("Exit")];
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
            new("  Install Enhanced"), new("  View status"), new("› Choose fixes", TerminalUi.Accent),
            new("  More options"), new("  Change language"), new(""), new("  Exit")];
        var frame = TerminalUi.RenderFrame(lines, 9, "↑ ↓ Navigate    Enter Select", width, height);
        var rows = Regex.Split(frame.Text, @"\x1b\[\d+;1H").Skip(1)
            .Select(row => Regex.Replace(row, @"\x1b\[[0-9;?]*[A-Za-z]", "")).ToArray();
        Check(rows.Length == height && rows.All(row => row.Length == width), "Every viewport cell must be painted without overflow.");
        Check(rows.Any(row => row.Contains("› Choose fixes")), "Selected option must remain visible at every tested size.");
        Check(string.Concat(rows).Contains("Enter Select"), "Keyboard hint must remain visible at every tested size.");
        Check(frame.Text.Contains(TerminalUi.Background) && frame.Text.Contains(TerminalUi.Accent), "Reference colors must appear in every frame.");
    }
    var sanitized = TerminalUi.RenderFrame([new("Bad path \x1b]0;not-a-title\a")], 0, null, 80, 24);
    Check(!sanitized.Text.Contains("\x1b]"), "User-supplied control characters must not alter the terminal.");
    Console.WriteLine($"Installer menu and rendering: {checks} checks passed.");
}
finally { Directory.Delete(fixture, recursive: true); }
