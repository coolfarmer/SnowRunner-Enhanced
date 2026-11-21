using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Spectre.Console;

namespace SnowRunnerEnhanced;

// Reference palette and spacing shared by every interactive installer screen.
internal sealed class TerminalUi : IDisposable
{
    internal const string Background = "\x1b[48;2;38;38;38m";
    internal const string Foreground = "\x1b[38;2;230;230;230m";
    internal const string Accent = "\x1b[38;2;0;215;255m";
    internal const string Muted = "\x1b[38;2;160;160;160m";
    internal const string Border = "\x1b[38;2;105;105;105m";
    internal const string Warning = "\x1b[38;2;245;195;100m";
    const int ContentWidth = 74;
    readonly List<Line> content = [];
    readonly nint output;
    readonly uint originalMode;
    bool disposed;

    internal sealed record Line(string Text, string Color = Foreground, bool Optional = false);
    internal sealed record Item(string Text, bool Enabled = true, bool BreakAfter = false);

    internal TerminalUi()
    {
        output = GetStdHandle(-11);
        if (!GetConsoleMode(output, out originalMode) || !SetConsoleMode(output, originalMode | 4))
            throw new IOException("This terminal does not support interactive rendering. Use --plain.");
        // Alternate screen and saved title keep the caller's terminal intact.
        Console.Write("\x1b[22;0t\x1b]0;SnowRunner Enhanced\x1b\\\x1b[?1049h\x1b[?25l");
        Console.CancelKeyPress += OnCancel;
    }

    internal void Header()
    {
        content.Clear();
        content.Add(new("", Optional: true));
        content.Add(new("╭" + new string('─', ContentWidth - 2) + "╮", Border));
        content.Add(new("│  S N O W R U N N E R".PadRight(ContentWidth - 1) + "│", Accent));
        content.Add(new("│  SnowRunner Enhanced".PadRight(ContentWidth - 1) + "│", Muted));
        content.Add(new("╰" + new string('─', ContentWidth - 2) + "╯", Border));
        Blank();
    }

    internal void Text(string text, string color = Foreground) => content.Add(new(text, color));
    internal void Blank() => content.Add(new("", Optional: true));
    internal void Detail(string label, string value) => Text(label.PadRight(20) + value, Muted);

    internal int Choose(string title, Item[] items, string hint, bool separator = false, bool spaceSelects = false)
    {
        int selected = Array.FindIndex(items, item => item.Enabled);
        if (selected < 0) throw new ArgumentException("The menu has no available options.");
        (int Width, int Height) size = default;
        bool redraw = true;
        while (true)
        {
            var currentSize = Size();
            if (redraw || currentSize != size)
            {
                size = currentSize;
                var lines = new List<Line>(content) { new(title, Accent) };
                if (separator) lines.Add(new(new string('─', ContentWidth), Border));
                lines.Add(new("", Optional: true));
                int focus = lines.Count;
                for (int i = 0; i < items.Length; i++)
                {
                    if (i == selected) focus = lines.Count;
                    lines.Add(new((i == selected ? "› " : "  ") + items[i].Text,
                        !items[i].Enabled ? Muted : i == selected ? Accent : Foreground));
                    if (items[i].BreakAfter) lines.Add(new(""));
                }
                lines.Add(new("", Optional: true));
                Draw(lines, focus, hint);
                redraw = false;
            }
            if (!Console.KeyAvailable) { Thread.Sleep(40); continue; }
            var key = Console.ReadKey(intercept: true).Key;
            if (key == ConsoleKey.Enter || (spaceSelects && key == ConsoleKey.Spacebar)) return selected;
            if (key == ConsoleKey.Escape) return -1;
            int next = MoveSelection(items, selected, key);
            redraw = next != selected;
            selected = next;
        }
    }

    internal static int MoveSelection(Item[] items, int selected, ConsoleKey key)
    {
        if (key == ConsoleKey.Home) return Array.FindIndex(items, item => item.Enabled);
        if (key == ConsoleKey.End) return Array.FindLastIndex(items, item => item.Enabled);
        int step = key == ConsoleKey.UpArrow ? -1 : key == ConsoleKey.DownArrow ? 1 : 0;
        if (step == 0) return selected;
        for (int i = 0, next = selected; i < items.Length; i++)
        {
            next = (next + step + items.Length) % items.Length;
            if (items[next].Enabled) return next;
        }
        return selected;
    }

    internal string ReadLine()
    {
        var lines = new List<Line>(content) { new("› ", Accent) };
        var position = Draw(lines, lines.Count - 1);
        Console.Write($"\x1b[{position.Row + 1};{position.Margin + 3}H{Foreground}\x1b[?25h");
        try { return Console.ReadLine() ?? throw new OperationCanceledException(); }
        finally { Console.Write("\x1b[?25l"); }
    }

    internal void Wait(string prompt)
    {
        // Long diagnostics remain readable a page at a time in small terminals.
        var lines = Wrap(content, Math.Max(8, Math.Min(ContentWidth, Size().Width - 6)));
        int pageHeight = Math.Max(1, Size().Height - 3);
        for (int start = 0; start < lines.Count; start += pageHeight)
        {
            var page = lines.Skip(start).Take(pageHeight).ToList();
            if (page.Count > 0 && !string.IsNullOrWhiteSpace(page[^1].Text)) page.Add(new(""));
            Draw(page, page.Count - 1, prompt);
            ConsoleKey key;
            do { key = Console.ReadKey(intercept: true).Key; }
            while (key is not (ConsoleKey.Enter or ConsoleKey.Escape));
            if (key == ConsoleKey.Escape) return;
        }
    }

    internal void Show() => Draw(content, content.Count - 1);

    internal void RunWithSpinner(string message, Action operation)
    {
        var lines = new List<Line>(content) { new("", Accent) };
        try
        {
            RunWithSpinner(operation, frame =>
            {
                lines[^1] = new(frame + " " + message, Accent);
                Draw(lines, lines.Count - 1);
            });
        }
        finally { Show(); }
    }

    internal static void RunWithSpinner(Action operation, Action<string> drawFrame)
    {
        var spinner = Spinner.Known.Dots;
        int frame = 0;
        drawFrame(spinner.Frames[frame]);
        var visible = Stopwatch.StartNew();
        // The entire synchronous transaction stays on one worker thread, including
        // acquiring and releasing its mutex. Only this thread renders the terminal.
        var work = Task.Run(operation);
        try
        {
            while (!work.IsCompleted || visible.Elapsed < TimeSpan.FromSeconds(1))
            {
                Thread.Sleep(spinner.Interval);
                if (!work.IsCompleted || visible.Elapsed < TimeSpan.FromSeconds(1))
                    drawFrame(spinner.Frames[++frame % spinner.Frames.Count]);
            }
        }
        finally
        {
            // Finish the transaction even if rendering fails, and preserve the
            // original installation exception for the existing error screen.
            work.GetAwaiter().GetResult();
        }
    }

    (int Row, int Margin) Draw(List<Line> lines, int focus, string? footer = null)
    {
        var size = Size();
        var frame = RenderFrame(lines, focus, footer, size.Width, size.Height);
        Console.Write(frame.Text);
        return (frame.FocusRow, frame.Margin);
    }

    // Pure frame construction also lets tests check clipping and background coverage.
    internal static (string Text, int FocusRow, int Margin) RenderFrame(
        List<Line> lines, int focus, string? footer, int width, int height)
    {
        width = Math.Max(12, width); height = Math.Max(4, height);
        int margin = width >= 40 ? 3 : 1;
        int available = Math.Min(ContentWidth, width - margin * 2);
        var before = Wrap(lines.Take(Math.Max(0, focus)), available);
        var wrapped = Wrap(lines, available);
        int focusRow = before.Count;
        var foot = footer == null ? [] : Wrap([new(footer, Muted)], available);
        int bodyHeight = height - foot.Count;
        for (int i = 0; wrapped.Count > bodyHeight && i < wrapped.Count;)
        {
            if (wrapped[i].Optional)
            {
                wrapped.RemoveAt(i);
                if (i < focusRow) focusRow--;
            }
            else i++;
        }
        int first = Math.Clamp(focusRow - bodyHeight + 1, 0, Math.Max(0, wrapped.Count - bodyHeight));
        var visible = wrapped.Skip(first).Take(bodyHeight).ToList();
        focusRow -= first;
        if (foot.Count > 0) visible.AddRange(foot);
        var result = new StringBuilder("\x1b[?25l\x1b[H" + Background);
        for (int row = 0; row < height; row++)
        {
            // Explicit positioning avoids a bottom-right newline scrolling the UI.
            result.Append($"\x1b[{row + 1};1H").Append(Background);
            if (row < visible.Count)
            {
                var line = visible[row];
                result.Append(line.Color).Append(' ', margin);
                if (line.Text.StartsWith('│') && line.Text.EndsWith('│'))
                    result.Append(Border).Append('│').Append(line.Color).Append(line.Text[1..^1]).Append(Border).Append('│');
                else result.Append(line.Text);
                result.Append(' ', Math.Max(0, width - margin - line.Text.Length));
            }
            else result.Append(' ', width);
        }
        return (result.ToString(), Math.Clamp(focusRow, 0, height - 1), margin);
    }

    static List<Line> Wrap(IEnumerable<Line> lines, int width)
    {
        var result = new List<Line>();
        foreach (var line in lines)
        {
            foreach (var part in line.Text.Replace("\r", "").Split('\n'))
            {
                string remaining = part.Replace('\t', ' ');
                // Control characters in user-entered paths must never become terminal commands.
                remaining = new string(remaining.Where(c => !char.IsControl(c)).ToArray());
                if (remaining.StartsWith('╭') || remaining.StartsWith('╰'))
                    remaining = remaining[0] + new string('─', width - 2) + remaining[^1];
                else if (remaining.StartsWith('│') && remaining.EndsWith('│'))
                    remaining = remaining[..Math.Min(remaining.Length - 1, width - 1)].PadRight(width - 1) + "│";
                else if (remaining.Length > width && remaining.All(c => c == '─')) remaining = new string('─', width);
                while (remaining.Length > width)
                {
                    int split = remaining.LastIndexOf(' ', width - 1, width);
                    if (split <= 2) split = width;
                    result.Add(new(remaining[..split], line.Color));
                    remaining = remaining[split..].TrimStart();
                }
                result.Add(new(remaining, line.Color, line.Optional));
            }
        }
        return result;
    }

    static (int Width, int Height) Size() => (Math.Max(12, Console.WindowWidth), Math.Max(4, Console.WindowHeight));

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        Console.CancelKeyPress -= OnCancel;
        Console.Write("\x1b[0m\x1b[?25h\x1b[?1049l\x1b[23;0t");
        SetConsoleMode(output, originalMode);
    }

    void OnCancel(object? sender, ConsoleCancelEventArgs args) => Dispose();

    [DllImport("kernel32.dll")] static extern nint GetStdHandle(int handle);
    [DllImport("kernel32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool GetConsoleMode(nint handle, out uint mode);
    [DllImport("kernel32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool SetConsoleMode(nint handle, uint mode);
}
