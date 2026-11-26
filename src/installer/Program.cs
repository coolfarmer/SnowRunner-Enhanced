using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Spectre.Console;

namespace SnowRunnerEnhanced;

internal static class Program
{
    static bool french, plain, json;
    static TerminalUi? ui;
    static bool automaticGameDirectory;
    static string T(string fr, string en) => french ? fr : en;
    static string FeatureName => T("Utilisation simultanée de la souris et du volant", "Simultaneous Mouse & Wheel Input");
    static readonly Color Accent = new(0, 200, 255);
    sealed record Choice(string Id, string Text, bool BreakAfter = false, bool Enabled = true);

    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        french = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "fr";
        json = args.Contains("--json");
        plain = args.Contains("--plain") || Console.IsOutputRedirected || Console.IsInputRedirected;
        try
        {
            var options = Parse(args);
            json = options.ContainsKey("json");
            plain = options.ContainsKey("plain") || Console.IsOutputRedirected || Console.IsInputRedirected;
            if (options.TryGetValue("language", out var language))
            {
                if (language is not ("fr" or "en")) throw new ArgumentException("--language fr|en");
                french = language == "fr";
            }
            if (options.ContainsKey("help")) { Help(); return 0; }
            if (!plain && !options.ContainsKey("action")) ui = new TerminalUi();
            if (options.ContainsKey("preview")) { Preview(); return 0; }
            if (options.TryGetValue("action", out var action)) return Command(options, action);
            if (json) throw new ArgumentException("--json requires --action.");
            if (!options.ContainsKey("language"))
                SelectLanguage();
            return Interactive(options.GetValueOrDefault("game-directory"));
        }
        catch (OperationCanceledException) { return 0; }
        catch (Exception error)
        {
            if (json) Console.WriteLine(JsonSerializer.Serialize(new { ok = false, error = error.Message }));
            else
            {
                Say(T("Action interrompue : ", "Action stopped: ") + error.Message, error: true);
                if (ui != null) Pause();
            }
            return 2;
        }
        finally { ui?.Dispose(); ui = null; }
    }

    static Dictionary<string, string> Parse(string[] args)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        var flags = new[] { "plain", "json", "help", "preview" };
        var values = new[] { "action", "game-directory", "wheel-mouse", "skip-startup-logos", "map", "general-improvements", "vehicle", "steering-wheel-improvements", "language" };
        for (int i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--")) throw new ArgumentException("Unknown argument: " + args[i]);
            var key = args[i][2..];
            if (result.ContainsKey(key)) throw new ArgumentException("Repeated option: " + key);
            if (flags.Contains(key)) result.Add(key, "true");
            else if (values.Contains(key) && i + 1 < args.Length) result.Add(key, args[++i]);
            else throw new ArgumentException("Unknown or incomplete option: " + key);
        }
        return result;
    }

    static string Sources => Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, ".."));
    static Installation Open(string directory) => new(directory, Sources, french);
    static bool BooleanOption(Dictionary<string, string> options, bool? fallback = null)
    {
        if (options.TryGetValue("wheel-mouse", out var value) && bool.TryParse(value, out var enabled)) return enabled;
        if (!options.ContainsKey("wheel-mouse") && fallback.HasValue) return fallback.Value;
        throw new ArgumentException("--wheel-mouse true|false is required.");
    }

    static bool? StartupOption(Dictionary<string,string> options, bool? fallback) {
        if (!options.TryGetValue("skip-startup-logos", out var value)) return fallback;
        if (bool.TryParse(value,out var flag)) return flag;
        throw new ArgumentException("--skip-startup-logos true|false is required.");
    }

    static bool? FeatureOption(Dictionary<string,string> options, string key, bool? fallback) {
        if (!options.TryGetValue(key, out var value)) return fallback;
        if (bool.TryParse(value, out var flag)) return flag;
        throw new ArgumentException($"--{key} true|false is required.");
    }

    static int Command(Dictionary<string, string> options, string action)
    {
        if (!options.TryGetValue("game-directory", out var directory)) throw new ArgumentException("--game-directory is required.");
        var installation = Open(directory);
        JsonObject result;
        switch (action)
        {
            case "check": case "status": result = installation.Inspect(); break;
            case "install": installation.Install(FeatureOption(options, "wheel-mouse", null), StartupOption(options, null),
                FeatureOption(options, "map", null), FeatureOption(options, "general-improvements", null), FeatureOption(options, "vehicle", null), FeatureOption(options, "steering-wheel-improvements", null)); result = installation.Inspect(); break;
            case "configure": installation.Configure(FeatureOption(options, "wheel-mouse", null), StartupOption(options, null),
                FeatureOption(options, "map", null), FeatureOption(options, "general-improvements", null), FeatureOption(options, "vehicle", null), FeatureOption(options, "steering-wheel-improvements", null)); result = installation.Inspect(); break;
            case "uninstall":
                result = new JsonObject { ["installed"] = false,
                    ["preserved"] = JsonSerializer.SerializeToNode(installation.Uninstall()) }; break;
            case "report":
                result = new JsonObject { ["report"] = SaveReport(installation) }; break;
            default: throw new ArgumentException("Unknown action: " + action);
        }
        if (json) Console.WriteLine(new JsonObject { ["ok"] = true, ["result"] = result }.ToJsonString());
        else if (action is "check" or "status") ShowStatus(result);
        else if (action == "report") Say(T("Diagnostic enregistré : ", "Diagnostic saved: ") + result["report"]!.GetValue<string>());
        else Say(T("Action terminée.", "Action completed."));
        return 0;
    }

    static void Say(string message, bool error = false)
    {
        if (ui != null) ui.Text(message, error ? TerminalUi.Warning : TerminalUi.Foreground);
        else if (plain) Console.WriteLine(message);
        else AnsiConsole.MarkupLine($"[{(error ? "yellow" : "grey85")}]{Markup.Escape(message)}[/]");
    }
    static void Header()
    {
        if (ui != null) ui.Header();
        else if (plain)
        {
            Console.WriteLine("\nSnowRunner Enhanced | " + Installation.Version);
            Console.WriteLine(T("Préversion · validation en jeu à terminer", "Preview · in-game validation pending"));
        }
        else
        {
            AnsiConsole.Write(new Rule("[bold #00c8ff]SnowRunner Enhanced[/]").LeftJustified());
            AnsiConsole.MarkupLine("[grey62]" + Installation.Version + "  ·  " +
                T("Préversion · validation en jeu à terminer", "Preview · in-game validation pending") + "[/]\n");
        }
    }

    static void Screen()
    {
        if (!plain && ui == null) AnsiConsole.Clear();
        Header();
    }

    static void Blank() { if (ui != null) ui.Blank(); else Console.WriteLine(); }
    static void Detail(string label, string value)
    {
        if (ui != null) ui.Detail(label, value);
        else Say(label.PadRight(20) + value);
    }
    static void SelectLanguage()
    {
        Screen();
        var language = Choose("Choisissez votre langue / Choose your language", [
            new("fr", "Français"), new("en", "English"), new("quit", "Quitter / Exit")],
            hint: "↑ ↓  Naviguer / Navigate    Entrée / Enter");
        if (language == "quit") throw new OperationCanceledException();
        french = language == "fr";
    }

    static string Choose(string title, Choice[] choices, bool separator = false, string? hint = null)
    {
        if (ui != null)
        {
            int selected = ui.Choose(title, choices.Select(c => new TerminalUi.Item(c.Text, c.Enabled, c.BreakAfter)).ToArray(),
                hint ?? T("↑ ↓ Naviguer    Entrée Sélectionner", "↑ ↓ Navigate    Enter Select"), separator);
            if (selected >= 0) return choices[selected].Id;
            return choices.FirstOrDefault(c => c.Id is "back" or "no" or "quit")?.Id
                ?? throw new OperationCanceledException();
        }
        Console.WriteLine(title);
        for (int i = 0; i < choices.Length; i++)
        {
            Console.WriteLine($"  {i + 1}. {choices[i].Text}" + (choices[i].Enabled ? "" : T(" (indisponible)", " (unavailable)")));
            if (choices[i].BreakAfter) Console.WriteLine();
        }
        while (true)
        {
            Console.Write("> ");
            var line = Console.ReadLine();
            if (line == null) throw new OperationCanceledException();
            if (int.TryParse(line, out int index) && index >= 1 && index <= choices.Length && choices[index - 1].Enabled) return choices[index - 1].Id;
            Say(T("Choisissez un numéro de la liste.", "Choose a number from the list."));
        }
    }
    static string? ReadPath()
    {
        Screen();
        Say(T("Dans Steam, faites un clic droit sur SnowRunner, puis Gérer > Parcourir les fichiers locaux.",
              "In Steam, right-click SnowRunner, then choose Manage > Browse local files."));
        Say(T("Copiez le chemin du dossier depuis la barre d’adresse et collez-le ici. Le dossier contenant SnowRunner.exe convient aussi.",
              "Copy the folder path from the address bar and paste it here. The folder containing SnowRunner.exe works too."));
        while (true)
        {
            Say(T("Chemin du dossier (Entrée pour revenir) :", "Folder path (press Enter to go back):"));
            var path = ui != null ? ui.ReadLine() : Console.ReadLine() ?? throw new OperationCanceledException();
            if (string.IsNullOrWhiteSpace(path)) return null;
            try { return Installation.FindGameDirectory(path); }
            catch (Exception error) when (error is IOException or ArgumentException or UnauthorizedAccessException or System.Security.SecurityException)
            {
                Say(T("SnowRunner n’a pas été trouvé dans ce dossier, ou le dossier est inaccessible. Vérifiez le chemin et réessayez.",
                      "We couldn’t find SnowRunner in that folder, or couldn’t access it. Check the path and try again."), true);
            }
        }
    }
    static string SelectGame(bool autoSelect = false)
    {
        string[] detected;
        try { detected = Installation.DetectGames().ToArray(); }
        catch (Exception error) when (error is IOException or ArgumentException or UnauthorizedAccessException or System.Security.SecurityException)
        { detected = []; }
        return ChooseGame(detected, autoSelect);
    }
    static string ChooseGame(string[] detected, bool autoSelect)
    {
        if (autoSelect && detected.Length == 1) { automaticGameDirectory = true; return detected[0]; }
        var choices = detected.Select((p, i) => new Choice(i.ToString(), p)).ToList();
        choices.Add(new("manual", T("Saisir le chemin du dossier", "Enter the folder path"), BreakAfter: true));
        choices.Add(new("quit", T("Quitter", "Exit")));
        while (true)
        {
            Screen();
            if (detected.Length == 0)
                Say(T("Nous n’avons pas trouvé SnowRunner automatiquement. S’il est installé, indiquez-nous simplement son dossier.",
                      "We couldn’t find SnowRunner automatically. If it’s installed, just point us to its folder."));
            else if (detected.Length > 1)
                Say(T("Plusieurs installations de SnowRunner ont été trouvées. Choisissez celle à utiliser.",
                      "We found more than one SnowRunner installation. Choose the one you’d like to use."));
            var choice = Choose(T("Où SnowRunner est-il installé ?", "Where is SnowRunner installed?"), choices.ToArray());
            if (choice == "quit") throw new OperationCanceledException();
            if (choice != "manual") { automaticGameDirectory = true; return detected[int.Parse(choice)]; }
            var path = ReadPath();
            if (path != null) { automaticGameDirectory = false; return path; }
        }
    }

    static int Interactive(string? directory)
    {
        automaticGameDirectory = false;
        Installation? installation = null;
        bool autoSelect = true;
        while (installation == null)
        {
            try { installation = Open(directory ?? SelectGame(autoSelect)); }
            catch (OperationCanceledException) { throw; }
            catch (Exception e) { Say(e.Message, true); Pause(); directory = null; autoSelect = false; }
        }
        bool pending = installation.HasReceipt ? ReadEnabled(installation) : true;
        bool pendingStartup = !installation.HasReceipt || installation.SkipStartupLogosEnabled;
        bool pendingMap = !installation.HasReceipt || installation.MapEnabled;
        bool pendingSteering = !installation.HasReceipt || installation.SteeringEnabled;
        bool pendingVehicle = !installation.HasReceipt || installation.VehicleEnabled;
        bool pendingGeneral = !installation.HasReceipt || installation.GeneralImprovementsEnabled;
        string? notice = null;
        while (true)
        {
            Screen();
            bool installed = installation.HasReceipt;
            bool migrate = installation.NeedsPreviewDefaults;
            Detail(T("Version Enhanced", "Enhanced version"), Installation.Version);
            Detail(T("Dossier du jeu", "Game folder"), automaticGameDirectory
                ? T("Détection automatique via Steam", "Automatic detection via Steam")
                : T("Dossier sélectionné manuellement", "Manually selected folder"));
            Blank();
            Say(T("Fermez SnowRunner avant toute modification.", "Close SnowRunner before making changes."));
            Blank();
            var enabled = installed ? ReadEnabled(installation) : pending;
            if (notice != null) { Say(notice); notice = null; }
            var action = Choose(T("MENU PRINCIPAL", "MAIN MENU"), [
                new("install", migrate ? T("Mettre à jour Enhanced", "Update Enhanced") : installed ? T("Enhanced est déjà installé", "Enhanced is already installed") : T("Installer Enhanced", "Install Enhanced"), Enabled: !installed || migrate),
                new("advanced", T("Options avancées", "Advanced Options")),
                new("more", T("Plus d’options", "More options")),
                new("help", T("Aide", "Help"), BreakAfter: true),
                new("quit", T("Quitter", "Exit"))], separator: true);
            if (action == "advanced") action = AdvancedOptions(installed);
            if (action == "more") action = MoreOptions(installation.GameDirectory);
            try
            {
                if (action is not ("quit" or "folder")) Screen();
                switch (action)
                {
                    case "quit": return 0;
                    case "back": break;
                    case "language": SelectLanguage(); break;
                    case "help": InteractiveHelp(); Pause(); break;
                    case "folder": installation = Open(SelectGame()); pending = installation.HasReceipt ? ReadEnabled(installation) : true; pendingStartup = !installation.HasReceipt || installation.SkipStartupLogosEnabled; pendingMap = !installation.HasReceipt || installation.MapEnabled; pendingGeneral = !installation.HasReceipt || installation.GeneralImprovementsEnabled; pendingVehicle = !installation.HasReceipt || installation.VehicleEnabled; pendingSteering = !installation.HasReceipt || installation.SteeringEnabled; break;
                    case "status":
                        ShowStatus(installation.Inspect());
                        Choose("", [new("back", T("Retour", "Back"))], hint: "");
                        break;
                    case "report": Say(T("Diagnostic enregistré : ", "Diagnostic saved: ") + SaveReport(installation));
                        Say(T("Joignez ce fichier à une issue dans le dépôt du projet. Aucun envoi automatique.",
                              "Attach this file to an issue in the project repository. Nothing is sent automatically.")); Pause(); break;
                    case "features":
                        var current = (Wheel: enabled, Startup: installed ? installation.SkipStartupLogosEnabled : pendingStartup,
                            Map: installed ? installation.MapEnabled : pendingMap, General: installed ? installation.GeneralImprovementsEnabled : pendingGeneral,
                            Vehicle: installed ? installation.VehicleEnabled : pendingVehicle, Steering: installed ? installation.SteeringEnabled : pendingSteering);
                        var selected = SelectEnhancements(current.Wheel, current.Startup, current.Map, current.General, current.Vehicle, current.Steering);
                        if (selected == null) break;
                        if (installed)
                        {
                            if (selected.Value != current || migrate)
                            {
                                Screen();
                                var message = T("Mise à jour du plugin en cours…", "Updating plugin…");
                                Action update = () => installation.Configure(selected.Value.Wheel, selected.Value.Startup, selected.Value.Map, selected.Value.General, selected.Value.Vehicle, selected.Value.Steering);
                                if (ui != null) ui.RunWithSpinner(message, update);
                                else
                                {
                                    Say(message);
                                    TerminalUi.RunWithSpinner(update, _ => { });
                                }
                            }
                        }
                        else { pending = selected.Value.Wheel; pendingStartup = selected.Value.Startup; pendingMap = selected.Value.Map; pendingGeneral = selected.Value.General; pendingVehicle = selected.Value.Vehicle; pendingSteering = selected.Value.Steering; }
                        notice = T("Choix enregistré.", "Selection saved."); break;
                    case "install":
                        if (ui != null)
                            ui.RunWithSpinner(T("Installation en cours…", "Installing Enhanced…"), () => installation.Install(pending, pendingStartup, pendingMap, pendingGeneral, pendingVehicle, pendingSteering));
                        else
                        {
                            Say(T("Installation en cours…", "Installing Enhanced…"));
                            installation.Install(pending, pendingStartup, pendingMap, pendingGeneral, pendingVehicle, pendingSteering);
                        }
                        Say(T("Installation terminée. Lancez le jeu normalement.", "Installed. Start the game normally."));
                        Pause();
                        break;
                    case "uninstall":
                        if (Confirm(T("Désinstaller Enhanced de SnowRunner ?", "Uninstall Enhanced from SnowRunner?")))
                        {
                            string[] retained = [];
                            if (ui != null)
                                ui.RunWithSpinner(T("Désinstallation en cours…", "Uninstalling Enhanced…"), () => retained = installation.Uninstall());
                            else
                            {
                                Say(T("Désinstallation en cours…", "Uninstalling Enhanced…"));
                                retained = installation.Uninstall();
                            }
                            Say(T("Enhanced a été désinstallé.", "Enhanced has been uninstalled."));
                            if (retained.Length != 0) Say(T("Fichiers conservés : ", "Files retained: ") + string.Join(", ", retained));
                            if (retained.Contains(Installation.LoaderName))
                            {
                                Blank();
                                Say(T("dinput8.dll est conservé : ce chargeur peut servir à d’autres mods.",
                                      "dinput8.dll is kept because this loader may be used by other mods."));
                            }
                            Pause();
                        }
                        break;
                }
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception e) { Say(e.Message, true); Pause(); }
        }
    }

    static (bool Wheel, bool Startup, bool Map, bool General, bool Vehicle, bool Steering)? SelectEnhancements(bool wheel, bool startup, bool map, bool general, bool vehicle, bool steering)
    {
        if (ui == null) {
            bool w = Choose(FeatureName, [new("on", T("Activé", "Enabled")), new("off", T("Désactivé", "Disabled"))]) == "on";
            bool l = Choose("Skip Startup Logos", [new("on", T("Activé", "Enabled")), new("off", T("Désactivé", "Disabled"))]) == "on";
            bool m = Choose("Map Improvements/Options", [new("on", T("Activé", "Enabled")), new("off", T("Désactivé", "Disabled"))]) == "on";
            bool g = Choose("General Improvements", [new("on", T("Activé", "Enabled")), new("off", T("Désactivé", "Disabled"))]) == "on";
            bool v = Choose("Vehicle Improvement/Options", [new("on", T("Activé", "Enabled")), new("off", T("Désactivé", "Disabled"))]) == "on";
            bool s = Choose("Steering Wheel Improvements", [new("on", T("Activé", "Enabled")), new("off", T("Désactivé", "Disabled"))]) == "on";
            return (w,l,m,g,v,s);
        }
        bool selectedWheel=wheel, selectedStartup=startup, selectedMap=map, selectedGeneral=general, selectedVehicle=vehicle, selectedSteering=steering;
        while (true) {
            Screen();
            Say(T("Chaque amélioration peut être activée ou désactivée indépendamment.", "Each enhancement can be enabled or disabled independently."));
            Blank();
            int choice = ui.Choose(T("PERSONNALISER LES AMÉLIORATIONS", "CUSTOMIZE ENHANCEMENTS"), [
                new($"[{(selectedWheel ? "x" : " ")}] {FeatureName}"),
                new($"[{(selectedStartup ? "x" : " ")}] Skip Startup Logos"),
                new($"[{(selectedMap ? "x" : " ")}] Map Improvements/Options"),
                new($"[{(selectedGeneral ? "x" : " ")}] General Improvements"),
                new($"[{(selectedVehicle ? "x" : " ")}] Vehicle Improvement/Options"),
                new($"[{(selectedSteering ? "x" : " ")}] Steering Wheel Improvements", BreakAfter: true),
                new(T("Enregistrer", "Save")), new(T("Annuler", "Cancel"))],
                T("↑ ↓ Naviguer    Espace Basculer    Entrée Sélectionner", "↑ ↓ Navigate    Space Toggle    Enter Select"), separator: true, spaceSelects: true);
            if (choice is -1 or 7) return null;
            if (choice==6) return (selectedWheel,selectedStartup,selectedMap,selectedGeneral,selectedVehicle,selectedSteering);
            if (choice==5) selectedSteering=!selectedSteering;
            if (choice==4) selectedVehicle=!selectedVehicle;
            if (choice==3) selectedGeneral=!selectedGeneral;
            if (choice==2) selectedMap=!selectedMap;
            if (choice==0) selectedWheel=!selectedWheel;
            if (choice==1) selectedStartup=!selectedStartup;
        }
    }

    static string AdvancedOptions(bool installed)
    {
        Screen();
        return Choose(T("OPTIONS AVANCÉES", "ADVANCED OPTIONS"), [
            new("status", T("Voir l’état", "View status")),
            new("features", T("Personnaliser les améliorations", "Customize enhancements")),
            new("uninstall", T("Désinstaller Enhanced", "Uninstall Enhanced"), BreakAfter: true, Enabled: installed),
            new("back", T("Retour", "Back"))], separator: true);
    }
    static string MoreOptions(string directory)
    {
        Screen();
        Say(T("Dossier actuel :", "Current folder:")); Say(directory); Blank();
        return Choose(T("PLUS D’OPTIONS", "MORE OPTIONS"), [
            new("folder", T("Changer de dossier", "Change folder")),
            new("report", T("Exporter un diagnostic", "Export diagnostic")),
            new("language", T("Changer de langue", "Change language"), BreakAfter: true),
            new("back", T("Retour", "Back"))], separator: true);
    }
    static void InteractiveHelp()
    {
        Say(T("AIDE", "HELP")); Blank();
        Say(T("Tous les correctifs sont activés par défaut. Choisissez Installer Enhanced pour les installer immédiatement. Pour en désactiver, utilisez Options avancées > Personnaliser les améliorations avant ou après l’installation.",
              "All fixes are enabled by default. Choose Install Enhanced to install immediately. To disable fixes, use Advanced Options > Customize enhancements before or after installation."));
        Blank();
        Say(T("Fermez le jeu avant de modifier l’installation. Les changements s’appliquent au prochain lancement.",
              "Close the game before making changes. Your settings apply on the next launch."));
        Blank();
        Say(T("Options avancées permet de vérifier l’état, de personnaliser les améliorations et de désinstaller Enhanced. Plus d’options permet de changer de dossier ou de langue, ou d’exporter un diagnostic.",
              "Advanced Options lets you view status, customize enhancements, and uninstall Enhanced. More options lets you change the folder or language, or export a diagnostic."));
        Blank();
        Say(T("Préversion : la validation en jeu reste à terminer.", "Preview: in-game validation is still pending."));
        Blank();
    }
    static bool ReadEnabled(Installation installation)
    {
        try { return installation.Enabled; }
        catch (Exception error) when (error is IOException or InvalidDataException or JsonException or InvalidOperationException or FormatException)
        {
            Say(T("Configuration à corriger : ", "Configuration needs attention: ") + error.Message, true);
            return false;
        }
    }
    static bool Confirm(string title) => Choose(title, [new("no", T("Annuler", "Cancel")), new("yes", T("Continuer", "Continue"))]) == "yes";
    static void Pause(string? prompt = null)
    {
        prompt ??= T("Entrée pour continuer…", "Press Enter to continue…");
        if (ui != null) { ui.Wait(prompt); return; }
        Blank();
        Say(prompt);
        if (Console.ReadLine() == null) throw new OperationCanceledException();
    }
    static void FeatureSummary(bool enabled)
    {
        var value = enabled ? T("Activé", "Enabled") : T("Désactivé", "Disabled");
        if (ui != null) ui.Text($"[{(enabled ? "x" : " ")}] {FeatureName} — {value}", enabled ? TerminalUi.Accent : TerminalUi.Muted);
        else if (plain) Say($"[{(enabled ? "x" : " ")}] {FeatureName} — {value}");
        else AnsiConsole.Write(new Panel(new Markup($"[bold]{Markup.Escape(FeatureName)}[/]\n" +
            $"[{(enabled ? "#00c8ff" : "grey62")}]{value}[/]"))
            .Border(BoxBorder.Rounded).BorderColor(Accent).Padding(1, 0));
    }

    static void ShowStatus(JsonObject status)
    {
        var lines = StatusView.Build(status, french, ui?.AvailableWidth ?? 74);
        if (ui != null) ui.AddLines(lines);
        else foreach (var line in lines)
        {
            if (plain) Console.WriteLine(line.Text);
            else
            {
                foreach (var run in line.Runs ?? [new TerminalUi.Run(line.Text, line.Color)])
                    Console.Write(run.Color + run.Text);
                Console.WriteLine("\x1b[0m");
            }
        }
    }

    static string SaveReport(Installation installation)
    {
        var folder = Path.Combine(Sources, "Reports"); Installation.CheckPath(folder);
        Directory.CreateDirectory(folder);
        var path = Path.Combine(folder, "Enhanced-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..6] + ".json");
        var report = installation.Inspect(); report["createdUtc"] = DateTime.UtcNow.ToString("O");
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        JsonSerializer.Serialize(stream, report, Installation.Pretty);
        return path;
    }
    static void Preview()
    {
        Header();
        Say(T("Aperçu de l’interface — aucun fichier du jeu n’est modifié.", "Interface preview — no game files are changed."));
        FeatureSummary(true);
        Say(T("Installer · Personnaliser les améliorations · Diagnostic · Désinstaller", "Install · Customize enhancements · Diagnostic · Uninstall"));
        if (ui != null) Pause();
    }
    static void Help() => Console.WriteLine("SnowRunner Enhanced " + Installation.Version + "\n" +
        "Install.cmd [--language fr|en] [--plain] [--game-directory PATH]\n" +
        "--action check|status|install|configure|uninstall|report --game-directory PATH [--json]\n" +
        "--wheel-mouse true|false (install: true; configure: preserve current)\n--skip-startup-logos true|false (install: true; configure: preserve current)\n--map true|false (install: true; configure: preserve current)\n--general-improvements true|false (install: true; configure: preserve current)\n--vehicle true|false (new install: true; update/configure: preserve current)\n--steering-wheel-improvements true|false (new feature: true; update/configure: preserve current)\n--preview\n");
}
