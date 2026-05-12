import { Plugin, Notice, requestUrl, FileSystemAdapter } from 'obsidian';
import { PkmAiSettings, DEFAULT_SETTINGS, PkmAiSettingTab } from './settings';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';


function rotateLogIfTooLarge(filePath: string, maxBytes: number = 2_000_000): void {
    try {
        if (!fs.existsSync(filePath)) {
            return;
        }

        const stats = fs.statSync(filePath);

        if (stats.size < maxBytes) {
            return;
        }

        const rotatedPath = `${filePath}.1`;

        if (fs.existsSync(rotatedPath)) {
            fs.unlinkSync(rotatedPath);
        }

        fs.renameSync(filePath, rotatedPath);
    } catch (error) {
        console.error(`[PKM AI] Failed to rotate log file ${filePath}:`, error);
    }
}


export default class PkmAiPlugin extends Plugin {
	settings: PkmAiSettings;
	private serverProcess: ChildProcess | null = null;

	getCurrentVaultPath(): string | null {
		const adapter = this.app.vault.adapter;

		if (adapter instanceof FileSystemAdapter) {
			return adapter.getBasePath();
		}

		return null;
	}

	getPluginDir(): string {
		const vaultPath = this.getCurrentVaultPath();

		if (!vaultPath) {
			throw new Error('Could not detect current Obsidian vault path.');
		}

		if (!this.manifest.dir) {
			throw new Error('Plugin directory is undefined.');
		}

		return path.join(vaultPath, this.manifest.dir);
	}

	buildBackendPayload(): PkmAiSettings {
		const vaultPath = this.getCurrentVaultPath();

		if (!vaultPath) {
			throw new Error('Could not detect current Obsidian vault path.');
		}

		const payload = JSON.parse(JSON.stringify(this.settings));

		payload.vault.path = vaultPath;
		payload.vault.notes_root_dir =
			this.settings.vault.notes_root_dir?.trim() ?? '';

		payload.vault.ignored_dirs = this.settings.vault.ignored_dirs
			.split(',')
			.map((s: string) => s.trim())
			.filter((s: string) => s.length > 0);

		return payload;
	}

	async onload() {
		await this.loadSettings();

		try {
			const pluginDir = this.getPluginDir();
            
            const isWindows = process.platform === 'win32';
            const exeName = isWindows ? 'pkmai-server.exe' : 'pkmai-server';
            const exePath = path.join(pluginDir, 'bin', exeName);

            console.log(`[PKM AI] Booting local server from: ${exePath}`);
			
			const logsDir = path.join(pluginDir, 'logs');
			fs.mkdirSync(logsDir, { recursive: true });

			const outLogPath = path.join(logsDir, 'pkmai-server.out.log');
			const errLogPath = path.join(logsDir, 'pkmai-server.err.log');

			rotateLogIfTooLarge(outLogPath);
			rotateLogIfTooLarge(errLogPath);

			const outLog = fs.openSync(outLogPath, 'a');
			const errLog = fs.openSync(errLogPath, 'a');

			this.serverProcess = spawn(exePath, [], {
				cwd: pluginDir,
				detached: false,
				windowsHide: true,
				stdio: ['ignore', outLog, errLog],
				env: {
					...process.env,
					TOKENIZERS_PARALLELISM: 'false',
					OMP_NUM_THREADS: '1',
					MKL_NUM_THREADS: '1',
					NUMEXPR_NUM_THREADS: '1',
				},
			});

			this.serverProcess.on('error', (error) => {
				console.error('[PKM AI] Server process error:', error);
				new Notice(`PKM AI server failed: ${error.message}`);
			});

			this.serverProcess.on('exit', (code, signal) => {
				console.log(`[PKM AI] Server exited. code=${code}, signal=${signal}`);
			});

            new Notice('PKM AI background engine started.');
        } catch (error) {
            console.error('[PKM AI] Failed to start background server:', error);
            new Notice('Failed to start the local AI server. Check console.');
        }
		
		this.addSettingTab(new PkmAiSettingTab(this.app, this));

		this.addRibbonIcon('link', 'Generate Auto-Links', async () => {
			await this.triggerApi('/api/v1/links/sync', 'Auto-Links');
		});

		this.addRibbonIcon('users', 'Generate Author Mirrors', async () => {
			await this.triggerApi('/api/v1/mirror/sync', 'Author Mirrors');
		});
	}

	async loadSettings() {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
	}

	async saveSettings() {
		await this.saveData(this.settings);
	}

	async triggerApi(endpoint: string, taskName: string) {
		const statusBarItem = this.addStatusBarItem();
		statusBarItem.addClass('pkmai-status-bar-item');
		statusBarItem.addClass('pkmai-status-processing');
		statusBarItem.setText(`⏳ ${taskName}: Initializing...`);

		try {
			const payload = this.buildBackendPayload();

			const response = await requestUrl({
				url: `http://127.0.0.1:8000${endpoint}`,
				method: 'POST',
                contentType: 'application/json',
                body: JSON.stringify(payload) 
			});
			
			if (response.status === 200) {
				const taskId = response.json.task_id;
				this.pollTaskStatus(taskId, taskName, statusBarItem);
			} else {
				statusBarItem.setText(`❌ ${taskName}: Server Error`);
				setTimeout(() => statusBarItem.remove(), 5000);
			}
		} catch (error) {
			statusBarItem.setText(`❌ ${taskName}: Connection Failed`);
			setTimeout(() => statusBarItem.remove(), 5000);		}
	}

	pollTaskStatus(taskId: string, taskName: string, statusBar: HTMLElement) {
		const interval = setInterval(async () => {
			try {
				const res = await requestUrl(`http://127.0.0.1:8000/api/v1/tasks/${taskId}`);
				const status = res.json.status;

				if (status === 'completed') {
					statusBar.setText(`✅ ${taskName}: Complete!`);
					statusBar.removeClass('pkmai-status-processing');
                    statusBar.addClass('pkmai-status-success');
					clearInterval(interval);
					new Notice(`${taskName} finished successfully!`);
					
					setTimeout(() => statusBar.remove(), 5000);
					
				} else if (typeof status === 'string' && status.startsWith('failed')) {
					statusBar.setText(`❌ ${taskName}: Error occurred`);
					statusBar.removeClass('pkmai-status-processing');
                    statusBar.addClass('pkmai-status-error');
					clearInterval(interval);
					new Notice(`Error running ${taskName}. Check the Python terminal.`);
					setTimeout(() => statusBar.remove(), 5000);
					
				} else {
					statusBar.setText(`⏳ ${taskName}: ${status}`);
				}
			} catch (e) {
				clearInterval(interval);
				statusBar.setText(`❌ ${taskName}: Disconnected`);
				setTimeout(() => statusBar.remove(), 5000);
			}
		}, 1000);
	}

	async triggerUndo(endpoint: string, taskName: string): Promise<void> {
		try {
			const payload = this.buildBackendPayload();

			const response = await requestUrl({
				url: `http://127.0.0.1:8000${endpoint}`,
				method: 'POST',
				contentType: 'application/json',
				body: JSON.stringify(payload),
			});

			if (response.status !== 200) {
				new Notice(`${taskName} cleanup failed. Check logs.`);
				return;
			}

			const result = response.json;

			if (endpoint.includes('/links/')) {
				new Notice(
					`${taskName} cleanup complete. Updated ${result.updated_notes} notes.`,
				);
			} else {
				new Notice(
					`${taskName} cleanup complete. Updated ${result.updated_notes} notes and deleted ${result.deleted_generated_notes} generated notes.`,
				);
			}
		} catch (error) {
			console.error(`[PKM AI] Failed to run cleanup for ${taskName}:`, error);
			new Notice(`${taskName} cleanup failed. Check logs.`);
		}
	}

	async onunload() {
        if (this.serverProcess) {
            console.log('[PKM AI] Shutting down background server...');
            this.serverProcess.kill();
            this.serverProcess = null;
        }
	}
}
