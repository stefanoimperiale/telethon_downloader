import asyncio
import os
import time

from yt_dlp import YoutubeDL

from env import YOUTUBE_FORMAT, YT_DL_TIMEOUT
from logger import logger


async def download_youtube_video(update, message, youtube_path, loop):
    try:
        url = message.message
        logger.info(f'INIT DOWNLOADING VIDEO YOUTUBE [{url}] ')
        task = loop.create_task(youtube_download(url, update, youtube_path))
        download_result = await asyncio.wait_for(task, timeout=YT_DL_TIMEOUT)
        logger.info(f'END DOWNLOADING VIDEO YOUTUBE [{url}] [{download_result}] ')

    except Exception as e:
        logger.info('ERROR: %s DOWNLOADING YT: %s' % (e.__class__.__name__, str(e)))
        await update.edit('ERROR: %s DOWNLOADING YT: %s' % (e.__class__.__name__, str(e)))


async def youtube_download(url, message, youtube_path):
    await message.edit(f'downloading...')

    try:
        ydl_opts = {'format': YOUTUBE_FORMAT, 'outtmpl': f'{youtube_path}/%(title)s.%(ext)s', 'cachedir': 'False',
                    "retries": 10, 'merge_output_format': 'mkv'}

        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            file_name = ydl.prepare_filename(info_dict)
            total_downloads = 1
            if '_type' in info_dict and info_dict["_type"] == 'playlist':
                total_downloads = len(info_dict['entries'])
                # logger.info('info_dict :::::::::::: [{}][{}]'.format(info_dict["_type"],len(info_dict['entries'])))
                youtube_path = os.path.join(youtube_path, info_dict['uploader'], info_dict['title'])
                ydl_opts = {'format': YOUTUBE_FORMAT, 'outtmpl': f'{youtube_path}/%(title)s.%(ext)s',
                            'cachedir': 'False', 'ignoreerrors': True, "retries": 10, 'merge_output_format': 'mkv'}
                ydl_opts.update(ydl_opts)
            else:
                youtube_path = os.path.join(youtube_path, info_dict['uploader'])
                ydl_opts = {'format': YOUTUBE_FORMAT, 'outtmpl': f'{youtube_path}/%(title)s.%(ext)s',
                            'cachedir': 'False', 'ignoreerrors': True, "retries": 10, 'merge_output_format': 'mkv'}
                ydl_opts.update(ydl_opts)

        with YoutubeDL(ydl_opts) as ydl:
            logger.info(f'DOWNLOADING VIDEO YOUTUBE [{url}] [{file_name}]')
            await message.edit(f'downloading {total_downloads} videos...')
            res_youtube = ydl.download([url])

            if not res_youtube:
                os.chmod(youtube_path, 0o777)
                filename = os.path.basename(file_name)
                logger.info(f'DOWNLOADED {total_downloads} VIDEO YOUTUBE [{file_name}] [{youtube_path}][{filename}]')
                end_time_short = time.strftime('%H:%M', time.localtime())
                await message.edit(f'Downloading finished {total_downloads} video at {end_time_short}\n{youtube_path}')
            else:
                logger.info(
                    f'ERROR: ONE OR MORE YOUTUBE VIDEOS NOT DOWNLOADED [{total_downloads}] [{url}] [{youtube_path}]')
                await message.edit(f'ERROR: one or more videos not downloaded')
    except Exception as e:
        logger.info('ERROR: %s DOWNLOADING YT: %s' % (e.__class__.__name__, str(e)))
        logger.info(f'ERROR: Exception ONE OR MORE YOUTUBE VIDEOS NOT DOWNLOADED')
