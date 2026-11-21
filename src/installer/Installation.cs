using System.Diagnostics;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace SnowRunnerEnhanced;

// Enhanced owns exactly these files. No ASI inventory, shared loader, or calls
// to another mod's tools are involved in any installation operation.
internal sealed class Installation
{
    internal const string Version = "0.1.0-preview.1";
    internal const string ConfigName = "SnowRunnerEnhanced.json";
    internal const string ReceiptName = "SnowRunnerEnhanced.install.json";
    internal const string StatusName = "SnowRunnerEnhanced.status.json";
    internal static readonly string[] Binaries = ["version.dll", "SnowRunnerEnhanced.dll"];
    internal static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true };
    internal string GameDirectory { get; }
    readonly string sources;
    readonly Dictionary<string, string> payload;
    string At(string name) => Path.Combine(GameDirectory, name);

    internal Installation(string directory, string sources)
    {
        GameDirectory = FindGameDirectory(directory);
        this.sources = Path.GetFullPath(sources);
        CheckPath(this.sources);
        var manifest = ReadJson(Path.Combine(this.sources, "package.json"));
        if (manifest["product"]?.GetValue<string>() != "SnowRunnerEnhanced" ||
            manifest["schemaVersion"]?.GetValue<int>() != 1 ||
            manifest["version"]?.GetValue<string>() != Version)
            throw new InvalidDataException("Package manifest is invalid.");
        payload = ReadHashes(manifest["payload"]);
        foreach (var name in Binaries)
        {
            var path = Path.Combine(this.sources, "Payload", name);
            CheckPath(path);
            if (Hash(path) != payload[name]) throw new InvalidDataException("Package file changed: " + name);
        }
    }

    internal static string FindGameDirectory(string path)
    {
        var full = Path.GetFullPath(path.Trim().Trim('"'));
        if (File.Exists(full) && Path.GetFileName(full).Equals("SnowRunner.exe", StringComparison.OrdinalIgnoreCase))
            full = Path.GetDirectoryName(full)!;
        foreach (var candidate in new[] { full, Path.Combine(full, "Sources", "Bin") })
            if (File.Exists(Path.Combine(candidate, "SnowRunner.exe")))
            {
                CheckPath(candidate);
                return candidate.TrimEnd(Path.DirectorySeparatorChar);
            }
        throw new FileNotFoundException("Select the folder containing SnowRunner.exe (or the SnowRunner installation folder).");
    }

    internal static void CheckPath(string path)
    {
        // Reject junction/symlink ancestors so our fixed filenames stay local.
        for (string? p = Path.GetFullPath(path); p != null; p = Path.GetDirectoryName(p))
        {
            try
            {
                if ((File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Linked paths are not supported: " + Path.GetFileName(p));
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
        }
    }

    void CheckExecutable()
    {
        var path = At("SnowRunner.exe"); CheckPath(path);
        using var stream = File.OpenRead(path);
        using var pe = new PEReader(stream);
        if (pe.PEHeaders.CoffHeader.Machine != Machine.Amd64 || pe.PEHeaders.PEHeader?.Magic != PEMagic.PE32Plus)
            throw new InvalidDataException("SnowRunner Windows x64 is required.");
        var imports = pe.PEHeaders.PEHeader.ImportTableDirectory;
        if (imports.RelativeVirtualAddress <= 0 || imports.Size < 20 || imports.Size > 1048576)
            throw new InvalidDataException("Unsupported executable import table.");
        var data = pe.GetSectionData(imports.RelativeVirtualAddress).GetContent(0, imports.Size).ToArray();
        for (int offset = 0; offset + 20 <= data.Length; offset += 20)
        {
            int rva = BitConverter.ToInt32(data, offset + 12);
            if (rva == 0) break;
            var name = pe.GetSectionData(rva).GetContent().Take(256).TakeWhile(b => b != 0).ToArray();
            if (Encoding.ASCII.GetString(name).Equals("version.dll", StringComparison.OrdinalIgnoreCase)) return;
        }
        throw new InvalidDataException("This executable does not import VERSION.dll; Enhanced cannot load through this package.");
    }

    internal static JsonObject ReadJson(string path)
    {
        CheckPath(path);
        if (new FileInfo(path).Length > 65536) throw new InvalidDataException("JSON file is too large.");
        return JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8), documentOptions:
            new JsonDocumentOptions { MaxDepth = 24 }) as JsonObject ?? throw new InvalidDataException("Invalid JSON object.");
    }

    static Dictionary<string, string> ReadHashes(JsonNode? node)
    {
        if (node is not JsonObject obj || obj.Count != Binaries.Length || Binaries.Any(n => !obj.ContainsKey(n)))
            throw new InvalidDataException("Invalid file inventory.");
        return Binaries.ToDictionary(n => n, n =>
        {
            var hash = obj[n]?.GetValue<string>() ?? "";
            if (!Regex.IsMatch(hash, "^[a-f0-9]{64}$")) throw new InvalidDataException("Invalid file hash.");
            return hash;
        });
    }

    internal static string Hash(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    internal static bool ParseFeature(JsonObject root)
    {
        if (root.Count != 2 || root["schemaVersion"]?.GetValue<int>() != 1 || root["features"] is not JsonObject features)
            throw new InvalidDataException("Invalid feature configuration.");
        if (features.Count == 0) return false;
        if (features.Count != 1 || features["wheel_mouse"] is not JsonObject wheel ||
            wheel.Count != 1 || wheel["enabled"] is not JsonValue value || !value.TryGetValue<bool>(out var enabled))
            throw new InvalidDataException("Unknown feature or invalid enabled value.");
        return enabled;
    }

    internal bool Enabled => ParseFeature(ReadJson(At(ConfigName)));
    internal bool HasReceipt => File.Exists(At(ReceiptName));
    static byte[] Configuration(bool enabled) => JsonSerializer.SerializeToUtf8Bytes(new
    {
        schemaVersion = 1, features = new { wheel_mouse = new { enabled } }
    }, Pretty);

    JsonObject Receipt()
    {
        var receipt = ReadJson(At(ReceiptName));
        if (receipt["product"]?.GetValue<string>() != "SnowRunnerEnhanced" || receipt["schemaVersion"]?.GetValue<int>() != 1)
            throw new InvalidDataException("Unrecognized installation receipt.");
        ReadHashes(receipt["files"]);
        return receipt;
    }

    internal JsonObject Inspect()
    {
        var report = new JsonObject { ["product"] = "SnowRunnerEnhanced", ["packageVersion"] = Version,
            ["installed"] = HasReceipt, ["activation"] = "Validated in memory on the next game launch" };
        try { CheckExecutable(); report["loaderSupported"] = true; }
        catch (Exception error) when (error is IOException or InvalidDataException or BadImageFormatException)
        { report["loaderSupported"] = false; report["loaderReason"] = "Unreadable or unsupported Windows x64 executable / VERSION import table."; }
        if (!HasReceipt)
        {
            report["conflicts"] = new JsonArray(Binaries.Append(ConfigName).Where(n => File.Exists(At(n)) || Directory.Exists(At(n)))
                .Select(n => (JsonNode?)JsonValue.Create(n)).ToArray());
            return report;
        }
        var receipt = Receipt();
        var hashes = ReadHashes(receipt["files"]);
        var files = new JsonObject();
        foreach (var (name, hash) in hashes)
        {
            CheckPath(At(name));
            files[name] = !File.Exists(At(name)) ? "missing" : Hash(At(name)) == hash ? "owned" : "modified";
        }
        report["installedVersion"] = receipt["version"]?.DeepClone();
        report["files"] = files;
        try { report["wheelMouseEnabled"] = Enabled; }
        catch (Exception error) when (error is IOException or InvalidDataException or JsonException or InvalidOperationException or FormatException)
        { report["configurationError"] = "Missing or invalid feature configuration."; }
        if (File.Exists(At(StatusName)))
        {
            // Keep runtime data typed/limited; do not include arbitrary files or paths.
            var runtime = ReadJson(At(StatusName));
            report["lastRun"] = new JsonObject();
            foreach (var key in new[] { "schemaVersion", "version", "gameSha256", "timeUtc", "processId", "features", "validation" })
                report["lastRun"]![key] = runtime[key]?.DeepClone();
        }
        return report;
    }

    IDisposable LockForChange()
    {
        CheckPath(GameDirectory);
        var mutexName = "Local\\SnowRunnerEnhanced.Setup." + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(GameDirectory.ToUpperInvariant())));
        var mutex = new Mutex(false, mutexName);
        bool acquired;
        try { acquired = mutex.WaitOne(0); } catch (AbandonedMutexException) { acquired = true; }
        if (!acquired) { mutex.Dispose(); throw new IOException("Another Enhanced installer is using this folder."); }
        try
        {
            var running = Process.GetProcessesByName("SnowRunner");
            bool any = running.Length != 0;
            foreach (var process in running) process.Dispose();
            if (any) throw new IOException("Close SnowRunner before changing the installation or its features.");
            foreach (var name in Binaries.Concat([ConfigName, ReceiptName, StatusName])) CheckPath(At(name));
            return new HeldMutex(mutex);
        }
        catch { mutex.ReleaseMutex(); mutex.Dispose(); throw; }
    }
    sealed class HeldMutex(Mutex mutex) : IDisposable
    {
        public void Dispose() { mutex.ReleaseMutex(); mutex.Dispose(); }
    }

    static void AtomicWrite(string path, byte[] bytes, bool replace)
    {
        CheckPath(path);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            File.Move(temporary, path, replace);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    static byte[] JsonBytes(JsonObject obj) => Encoding.UTF8.GetBytes(obj.ToJsonString(Pretty));

    internal void Install(bool enabled)
    {
        using var held = LockForChange();
        CheckExecutable();
        if (HasReceipt) throw new IOException("Enhanced is already installed. Use Features or uninstall before replacing the package.");
        foreach (var name in Binaries.Concat([ConfigName, ReceiptName]))
            if (File.Exists(At(name)) || Directory.Exists(At(name)))
                throw new IOException("Existing file preserved: " + name + ". Resolve this conflict before installing Enhanced.");
        var config = Configuration(enabled);
        var receipt = new JsonObject { ["product"] = "SnowRunnerEnhanced", ["schemaVersion"] = 1, ["version"] = Version,
            ["files"] = JsonSerializer.SerializeToNode(payload), ["configurationSha256"] = Convert.ToHexStringLower(SHA256.HashData(config)),
            ["complete"] = false };
        var created = new List<string>();
        try
        {
            // A receipt written first makes an interrupted install recoverable
            // using uninstall, while ownership checks preserve changed files.
            AtomicWrite(At(ReceiptName), JsonBytes(receipt), false); created.Add(ReceiptName);
            foreach (var name in Binaries)
            {
                var data = File.ReadAllBytes(Path.Combine(sources, "Payload", name));
                if (Convert.ToHexStringLower(SHA256.HashData(data)) != payload[name]) throw new IOException("Payload changed during installation.");
                AtomicWrite(At(name), data, false); created.Add(name);
            }
            AtomicWrite(At(ConfigName), config, false); created.Add(ConfigName);
            receipt["complete"] = true;
            AtomicWrite(At(ReceiptName), JsonBytes(receipt), true);
        }
        catch
        {
            // Only files created by this transaction are eligible for rollback.
            foreach (var name in created.AsEnumerable().Reverse())
                try
                {
                    CheckPath(At(name));
                    var expected = name == ConfigName ? receipt["configurationSha256"]!.GetValue<string>() : payload.GetValueOrDefault(name);
                    if (name != ReceiptName && File.Exists(At(name)) && Hash(At(name)) == expected) File.Delete(At(name));
                }
                catch (IOException) { }
            // Keep the recovery receipt if any owned payload remains.
            if (created.Contains(ReceiptName) && !Binaries.Append(ConfigName).Any(n => File.Exists(At(n)))) File.Delete(At(ReceiptName));
            throw;
        }
    }

    internal void Configure(bool enabled)
    {
        using var held = LockForChange();
        var receipt = Receipt();
        VerifyBinaries(receipt, allowMissing: false);
        var old = File.ReadAllBytes(At(ConfigName));
        ParseFeature(ReadJson(At(ConfigName)));
        var config = Configuration(enabled);
        AtomicWrite(At(ConfigName), config, true);
        try
        {
            receipt["configurationSha256"] = Convert.ToHexStringLower(SHA256.HashData(config));
            AtomicWrite(At(ReceiptName), JsonBytes(receipt), true);
        }
        catch { AtomicWrite(At(ConfigName), old, true); throw; }
    }

    void VerifyBinaries(JsonObject receipt, bool allowMissing)
    {
        foreach (var (name, hash) in ReadHashes(receipt["files"]))
        {
            CheckPath(At(name));
            if (allowMissing && !File.Exists(At(name)) && !Directory.Exists(At(name))) continue;
            if (!File.Exists(At(name)) || Hash(At(name)) != hash)
                throw new IOException("Owned file is missing or changed; it was preserved: " + name);
        }
    }

    internal string[] Uninstall()
    {
        using var held = LockForChange();
        var receipt = Receipt();
        VerifyBinaries(receipt, allowMissing: true);
        // Hold every DLL with delete permission before removing anything, so
        // a running loader or a locked file cannot cause a partial uninstall.
        var handles = new List<FileStream>();
        try
        {
            foreach (var name in Binaries.Where(n => File.Exists(At(n))))
                handles.Add(new FileStream(At(name), FileMode.Open, FileAccess.Read, FileShare.Delete));
            foreach (var name in Binaries) File.Delete(At(name));
        }
        finally { foreach (var handle in handles) handle.Dispose(); }
        var preserved = new List<string>();
        if (File.Exists(At(ConfigName)))
        {
            if (Hash(At(ConfigName)) == receipt["configurationSha256"]?.GetValue<string>()) File.Delete(At(ConfigName));
            else preserved.Add(ConfigName);
        }
        // Diagnostics are deliberately retained for troubleshooting after removal.
        if (File.Exists(At(StatusName))) preserved.Add(StatusName);
        File.Delete(At(ReceiptName));
        return preserved.ToArray();
    }

    internal static IEnumerable<string> DetectGames()
    {
        var roots = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        // Steam's registry and VDF paths can use different slash styles.
        void AddRoot(string path) => roots.Add(Path.TrimEndingDirectorySeparator(Path.GetFullPath(path)));
        var steam = Registry.GetValue(@"HKEY_CURRENT_USER\Software\Valve\Steam", "SteamPath", null) as string;
        if (steam != null) AddRoot(steam);
        var standard = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Steam");
        if (Directory.Exists(standard)) AddRoot(standard);
        foreach (var root in roots.ToArray())
        {
            var libraries = Path.Combine(root, "steamapps", "libraryfolders.vdf");
            if (!File.Exists(libraries)) continue;
            foreach (Match match in Regex.Matches(File.ReadAllText(libraries), "\"path\"\\s*\"([^\"]+)\""))
                AddRoot(match.Groups[1].Value.Replace("\\\\", "\\"));
        }
        foreach (var root in roots)
        {
            var folder = Path.Combine(root, "steamapps", "common", "SnowRunner", "Sources", "Bin");
            if (File.Exists(Path.Combine(folder, "SnowRunner.exe"))) yield return folder;
        }
    }
}
