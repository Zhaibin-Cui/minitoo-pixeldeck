using System;
using System.IO;
using System.Text;
using System.Threading;
using Windows.Media;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Devices.Enumeration;
using Windows.Foundation;

// Event callbacks write JSONL directly to a pipe. No Pop(), file or timer polling.
public sealed class MediaBridge : IDisposable
{
    private readonly MediaPlayer player;
    private static readonly object outputLock = new object();
    private static long sequence;
    private readonly ManualResetEvent stop;

    private static string Quote(string text)
    {
        var result = new StringBuilder("\"");
        foreach (char ch in text ?? "")
        {
            if (ch == '"' || ch == '\\') { result.Append('\\'); result.Append(ch); }
            else if (ch < 32) result.Append("\\u" + ((int)ch).ToString("x4"));
            else result.Append(ch);
        }
        return result.Append('"').ToString();
    }

    private static void Emit(string type, string value)
    {
        lock (outputLock)
        {
            long id = ++sequence;
            Console.WriteLine("{\"type\":" + Quote(type) + ",\"value\":" + Quote(value) +
                ",\"sequence\":" + id + ",\"utc\":" + Quote(DateTime.UtcNow.ToString("o")) + "}");
            Console.Out.Flush();
        }
    }

    public MediaBridge(string endpointHint, string wavePath, ManualResetEvent stopEvent)
    {
        stop = stopEvent;
        var operation = DeviceInformation.FindAllAsync(DeviceClass.AudioRender);
        using (var ready = new ManualResetEvent(false))
        {
            operation.Completed = (result, status) => {
                // Cancellation may complete after the waiting scope has exited.
                try { ready.Set(); } catch (ObjectDisposedException) { }
            };
            if (!ready.WaitOne(8000)) { operation.Cancel(); throw new TimeoutException("Audio endpoint lookup timed out"); }
            if (operation.Status != AsyncStatus.Completed) throw new Exception("Audio endpoint lookup failed");
        }
        DeviceInformation selected = null;
        int matches = 0;
        foreach (var device in operation.GetResults())
        {
            if (device.Id.IndexOf(endpointHint, StringComparison.OrdinalIgnoreCase) >= 0 ||
                device.Name.IndexOf(endpointHint, StringComparison.OrdinalIgnoreCase) >= 0)
            { selected = device; matches++; }
        }
        if (matches != 1) throw new Exception("Configure audio_endpoint_hint to match exactly one MiniToo speaker output");
        player = new MediaPlayer();
        player.AudioDevice = selected;
        player.IsMuted = true;
        player.IsLoopingEnabled = true;
        var commands = player.CommandManager;
        commands.IsEnabled = true;
        commands.NextBehavior.EnablingRule = MediaCommandEnablingRule.Always;
        commands.PreviousBehavior.EnablingRule = MediaCommandEnablingRule.Always;
        commands.PlayBehavior.EnablingRule = MediaCommandEnablingRule.Always;
        commands.PauseBehavior.EnablingRule = MediaCommandEnablingRule.Always;
        commands.NextReceived += (sender, args) => { args.Handled = true; Emit("button", "Next"); };
        commands.PreviousReceived += (sender, args) => { args.Handled = true; Emit("button", "Previous"); };
        // Explicitly keep transport state aligned with remote Play/Pause commands.
        // Both remain enabled; each callback yields exactly one application event.
        commands.PlayReceived += (sender, args) => { args.Handled = true; player.Play(); Emit("button", "Play"); };
        commands.PauseReceived += (sender, args) => { args.Handled = true; player.Pause(); Emit("button", "Pause"); };
        player.MediaFailed += (sender, args) => { Emit("error", args.ErrorMessage); stop.Set(); };
        player.MediaOpened += (sender, args) => Emit("ready", selected.Name);
        var item = new MediaPlaybackItem(MediaSource.CreateFromUri(new Uri(Path.GetFullPath(wavePath))));
        var properties = item.GetDisplayProperties();
        properties.Type = MediaPlaybackType.Music;
        properties.MusicProperties.Title = "MiniToo Pixeldeck";
        properties.MusicProperties.Artist = "Silent input session";
        item.ApplyDisplayProperties(properties);
        player.Source = item;
        player.Play();
    }

    public void Dispose()
    {
        if (player != null)
        {
            player.SystemMediaTransportControls.IsEnabled = false;
            player.Dispose();
        }
    }

    [MTAThread]
    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (args.Length == 1 && args[0] == "--self-test-json")
        {
            Emit("button", "Next"); Emit("button", "Play"); Emit("button", "Pause");
            return 0; // Does not construct a MediaPlayer or access any device.
        }
        if (args.Length != 2) { Console.Error.WriteLine("Usage: MediaBridge.exe ENDPOINT_HINT SILENCE_WAV"); return 2; }
        using (var done = new ManualResetEvent(false))
        {
            Console.CancelKeyPress += (sender, e) => { e.Cancel = true; done.Set(); };
            var input = new Thread(() => {
                try { while (true) { string line = Console.ReadLine(); if (line == null || line == "stop") { done.Set(); return; } } }
                catch { done.Set(); }
            });
            input.IsBackground = true;
            input.Start();
            try
            {
                using (var bridge = new MediaBridge(args[0], args[1], done))
                    done.WaitOne();
                Emit("closed", "released");
                return 0;
            }
            catch (Exception ex) { Emit("error", ex.Message); return 1; }
        }
    }
}
