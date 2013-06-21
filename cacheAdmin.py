#!/usr/bin/python3
# -*- coding: utf-8 -*-
from cmd import Cmd
from datetime import date
from glob import glob
import stat
import os
import getopt
import urllib.request
import shutil
import fnmatch
import configparser
import http.client
import zipfile
import time
import traceback
import sys

# TODO
# - Criar um repositório especifico para esse projeto no github.
# - Implementar um refresh dos dados após a criação de uma base ou depois do
# addinfo
# - Incluir a possibilidade de abrir o log de uma base (semelhante ao que o
# Danilo fez)
# - Mudar o nome do arquivo "base.cfg" para <BASE>.cfg
# - Abandonar o uso do script "startup.sh", montar o comando dinamicamente e
# startar o subprocesso.
# - permitir a inclusão de N IPs por base
# - fazer funcionar o esquema de apelido p/ as bases.
# - Permitir startar uma base com IP interno ou externo

# Diretorio onde ficam localizadas as bases
DIRETORIO_PADRAO = "/home/ricardo/Bases"

# Diretorio default onde serão colocados os backups das bases
DIRETORIO_PADRAO_BACKUP = '/home/ricardo/tmp'

# Diretorios que requerem confirmação antes de serem deletados
DIRETORIOS_ESPECIAIS = (
    'profile',  # Pasta dos scripts abertos
)

# Arquivos que não devem ser apagados
ARQUIVOS_ESPECIAIS = (
    'iEngine.exe',
    'iengine.exe',
    'base.cfg',
    'startup.sh',
)

MENSAGEM_INICIAL = """\033[1;32m
========================================================
  ______   __ _    ____
 |  _ \ \ / // \  |  _ \\
 | | | \ V // _ \ | | | |
 | |_| || |/ ___ \| |_| |
 |____/ |_/_/   \_\____/

 Ferramenta de manipulação de bases da DYAD
 Usando Python 3.x
 Tecle 'help' para ver a lista de comandos (atalho='?')
 Tecle CTRL+D para sair
========================================================\033[1;m\n"""

PROMPT = "DYAD >>> "

LAYOUT_LISTA = "{:<20}{:<20}{:>10}{:^15}{:>10}"


class CacheAdmin():
    def __init__(self):
        self.config = configparser.RawConfigParser()
        # Muda o diretorio atual para o diretório onde estao as bases
        os.chdir(DIRETORIO_PADRAO)
        # A lista de clientes é lida dos diretorios que estão dentro do
        # diretorio padrao
        self.clientes = glob('*')
        # self.write( 'Clientes:\n'.join(self.clientes) )
        # O resultado do glob é no formaro "cliente/base". Testo se é uma base
        # valida e dou o split pela barra
        self.bases = [b.split(os.sep)[1] for b in glob(
            os.path.join('*', '*')) if self.base_valida(b)]
        # self.write( 'Bases:\n'.join(self.bases) )

    def write(self, texto):
        print('  ' + texto)

    def base_valida(self, base):
        if not os.path.isdir(base):
            return False
        if not os.path.isfile(os.path.join(base, 'base.cfg')):
            return False
        self.config.read(os.path.join(base, 'base.cfg'))
        nome = self.config.get('base', 'nome')
        if os.sep in base:
            return nome == base.split(os.sep)[1]
        return nome == base

    def get_autocomplete_bases(self, texto):
        return [b for b in self.bases if b.startswith(texto.upper())]

    def get_autocomplete_clientes(self, texto):
        return [cl for cl in self.clientes if cl.startswith(texto.upper())]

    def get_dir_size(self, fullpath):
        # TODO Verificar se tem como trocar o comando BASH por um equivalente
        # em python
        fResult = os.popen("du -sh {}".format(fullpath))
        result_lines = fResult.readlines()
        fResult.close()
        return result_lines[0].split('\t')[0]

    def get_last_acess(self, fullpath):
        # TODO Verificar se o os.stat também funciona no WINDOWS
        if not os.path.isdir(fullpath):
            return None
        exe = os.path.join(fullpath, "iengine.exe")
        if not os.path.isfile(exe):
            exe = fullpath  # se nao achou o EXE entao pega a data de ultimo acesso a pasta
        # data = date.fromtimestamp(os.stat( exe ).st_atime)
        data = date.fromtimestamp(os.stat(exe).st_mtime)
        return data.strftime("%d/%m/%Y")

    def get_client_bases(self, client):
        bases = []
        if not os.path.isdir(client):
            self.write("Erro! {} is not a diretory.".format(client))
            return
        for dirname in glob(os.path.join(client, '*')):
            bases.append({
                'nome': dirname.split(os.sep)[1],  # dirname <= 'cliente/base'
                'tamanho': self.get_dir_size(dirname),
                'ultimoacesso': self.get_last_acess(dirname),
                'status': self.ping(dirname)
            })
        return bases

    def list_bases(self, client=None):
        if not client:
            client = DIRETORIO_PADRAO
            client_list = self.clientes
        else:
            # fullpath = os.path.join( DIRETORIO_PADRAO, client )
            if not os.path.isdir(client):
                self.write("Erro! '{}' não é um diretório.".format(client))
                return
            client_list = [client]
        print(LAYOUT_LISTA.format(
            "Cliente", "Base", "Tamanho", "Ult.Acesso", "Status"))
        for cliente in client_list:
            # self.write( "->{}".format( cliente ) )
            base_list = self.get_client_bases(cliente)
            for base in base_list:
                # if not self.base_valida(base.get('nome')):
                #    continue
                print(LAYOUT_LISTA.format(
                    cliente,
                    base.get('nome'),
                    base.get('tamanho'),
                    base.get('ultimoacesso'),
                    base.get('status')))
            # print("\n")
        print("Espaço total:{}".format(self.get_dir_size(client)))

    def ask_parameters(self):
        op = {}
        op['cliente'] = input('\tInforme o nome do cliente(BRB, CASF etc): ')
        op['base'] = input('\tInforme o nome da base: ')
        op['apelido'] = input('\tInforme o apelido da base: ')
        op['url'] = input(
            '\tInforme a URL da base servidora(IP:PORTA): ').replace('http://', '')
        return op

    def create_folders(self, options):
        self.write("Criando pastas...")
        client_folder = options.get('cliente')
        base_folder = os.path.join(client_folder, options.get('base'))
        if not os.path.exists(client_folder):
            os.mkdir(client_folder)
        if not os.path.exists(base_folder):
            os.mkdir(base_folder)
        options['pastalocal'] = base_folder

    def download_engine(self, options):
        self.write("Obtendo o aplicativo iengine.exe do endereço {} ...".format(
            options.get('url')))
        url = os.path.join(options.get('url'), 'iengine.exe')
        if not url.startswith('http://'):
            url = "http://{}".format(url)
        temp_file = urllib.request.urlretrieve(url)
        dest_file = os.path.join(options.get('pastalocal'), 'iengine.exe')
        shutil.copy(temp_file[0], dest_file)
        if os.path.isfile(dest_file):
            options['iengine'] = dest_file
            return True
        return False

    def create_startup(self, options):
        # TODO Quando for adaptar p/ windows, remover a referencia ao wine,
        # pois nao precisará
        if not os.path.isfile(options.get('iengine')):
            self.write(
                "{} is not a valid file!".format(options.get('iengine')))
        scriptname = os.path.join(options.get('pastalocal'), 'startup.sh')
        scriptfile = open(scriptname, 'w')
        scriptfile.write('#!/bin/bash\n\n')
        scriptfile.write("wine '{}' {} {}  >{} 2>&1".format(
            options.get('iengine'),
            options.get('url'),
            options.get('base'),
            os.path.join(options.get('pastalocal'), 'wine.log')
        ))
        scriptfile.close()
        os.chmod(scriptname, stat.S_IRWXU | stat.S_IRWXG)
                 # Atribui permissao RWX ao usuario dono e ao grupo
        options['script'] = scriptname
        self.write("Script de startup da base: " + scriptname)

    def criar_arquivo_configuracao(self, options):
        configFileName = os.path.join(options.get('pastalocal'), 'base.cfg')
        config = configparser.RawConfigParser()
        config.add_section('base')
        config.set('base', 'url', options.get('url'))
        config.set('base', 'cliente', options.get('cliente'))
        config.set('base', 'nome', options.get('base'))
        config.set('base', 'apelido', options.get('apelido'))
        with open(configFileName, 'w') as configfile:
            config.write(configfile)
        self.write("Arquivo de configuração criado: {}".format(configFileName))

    def verifica_disponibilidade(self, base):
        self.write(base)
        if not base:
            base = '*'
        lista = glob(os.path.join('*', base))
        for diretorio in lista:
            self.write("Status da base {}: {}".format(
                diretorio, self.ping(diretorio)))

    def info(self, basename):
        if not basename:
            basename = input('\tNome da base que deseja consultar:')
        diretorio = glob(os.path.join('*', basename))[0]
        configFileName = os.path.join(diretorio, 'base.cfg')
        if not os.path.isfile(configFileName):
            self.write('File not found! ({})'.format(configFileName))
            return
        # config = configparser.RawConfigParser()
        try:
            self.config.read(configFileName)
            cliente = self.config.get('base', 'cliente')
            base = self.config.get('base', 'nome')
            url = self.config.get('base', 'url')
            self.write("Cliente:\t{}".format(cliente))
            self.write("Nome:\t\t{}".format(base))
            self.write("Local:\tfile://{}".format(
                os.path.join(DIRETORIO_PADRAO, diretorio)))
            self.write("Endereço:\thttp://{}".format(url))
            self.write("Manage:\thttp://{}/manage".format(url))
            self.write(
                "Espaço usado:\t{}".format(self.get_dir_size(diretorio)))
        except:
            self.write("Error")

    def ping(self, basedir):
        # print( "Verificando se a base {} está disponível no endereço
        # {}...".format( base, url ) )
        config = configparser.RawConfigParser()
        cfgname = os.path.join(basedir, 'base.cfg')
        if not os.path.isfile(cfgname):
            # return "\033[1;31mNO CFG\033[1;m"
            return "NO CFG"
        try:
            config.read(cfgname)
            url = config.get('base', 'url')
            con = http.client.HTTPConnection(url, None, None, timeout=2)
            con.request('HEAD', '/')
            res = con.getresponse()
            if res.status in (200, 302):
                # return "\033[1;32mOnline\033[1;m"
                return "Online"
            elif res.status in (202):
                # return "\033[1;33mLoading\033[1;m"
                return "Loading"
            else:
                # return "\033[1;31mOffline({})\033[1;m".format( res.status )
                return "Off({})".format(res.status)
        except:
            # return "\033[1;31mError\033[1;m"
            return "Error"

    def criar_base(self, options):
        if not options:
            options = self.ask_parameters()
        self.write(
            "Iniciando criação da base {} ...".format(options.get('base')))
        self.create_folders(options)
        if self.download_engine(options):
            self.create_startup(options)
            if input("\tDeseja criar atalho no bash para essa base?(S/N): ") in ('S', 's'):
                self.criar_atalho(options)

            self.criar_arquivo_configuracao(options)
            if input("\tDeseja carregar o cache?(S/N): ") in ('S', 's'):
                self.write("Iniciando carregamento do cache da base {}/{}...".format(
                    options.get('cliente'), options.get('base')))
                self.run_startup(options.get('script'))

    def criar_atalho(self, options):
        # TODO Na versao Windows essa funcionalidade será removida
        nome_atalho = input('\tInforme um apelido para a base: ')
        self.do_shell("echo '#Atalho para a base {}\nalias {}={}' >> ~/.bash_aliases".format(
            options.get('base'), nome_atalho, options.get('script')))

    def descartar_chave(self, nome_base):
        base_dir = glob(os.path.join('*', nome_base))[0]
        for dirname, dirnames, filenames in os.walk(base_dir):
            for filename in filenames:
                if fnmatch.fnmatch(filename.upper(), '*KEYCACHE*'):
                    self.write("Deletando arquivo {}".format(
                        os.path.join(dirname, filename)))
                    os.remove(os.path.join(dirname, filename))

    def descartar_cache(self, nome_base):
        pastas_da_base = [p for p in glob(
            os.path.join('*', nome_base, '*')) if os.path.isdir(p)]
        self.write("{} pasta(s)...".format(len(pastas_da_base)))
        for pasta in pastas_da_base:
            if pasta.split(os.sep)[2] in DIRETORIOS_ESPECIAIS:  # pasta <= 'cliente/base/pasta'
                if input("\tDeseja remover o diretório '{}'?(S/N): ".format(pasta)) in ('N', 'n'):
                    continue
            self.write("Removendo diretorio {}".format(pasta))
            shutil.rmtree(pasta)

    def descartar_base(self, nome_base):
        basedir = glob(os.path.join('*', nome_base))
        if len(basedir) == 0:
            self.write('Diretorio não encontrado!')
            return
        basedir = basedir[0]
        if input("\tDeseja remover o diretorio {}?(S/N): ".format(basedir)) in ('N', 'n'):
            self.write('Remoção da base cancelada pelo usuário.')
            return
        shutil.rmtree(basedir, ignore_errors=True)
        if os.path.isdir(basedir):
            self.write(
                'Algo aconteceu e o diretório não pode ser removido, apague-o manualmente.')
        else:
            self.write('Diretório da base {} removido com sucesso!'.format(
                nome_base))

    def backup(self, base, destino):
        # TODO Rever a referencia a '/', se nao pode ser trocada por os.sep
        nome_zip = "{}_{}.zip".format(base, time.strftime("_%Y_%m_%d"))
        nome_zip = os.path.join(destino, nome_zip)
        self.write("Arquivo: " + nome_zip)
        zipado = zipfile.ZipFile(nome_zip, "w")
        base_dir = glob(os.path.join('*', base))[0]
        for dirname, dirnames, filenames in os.walk(base_dir):
            # Processando arquivos do diretorio
            for filename in filenames:
                if fnmatch.fnmatch(filename.upper(), '*KEYCACHE*'):
                    continue
                # dir_aux = dirname.replace(DIRETORIO_PADRAO, '')
                # cliente = dir_aux.split( os.sep )[1]
                # dir_aux = dir_aux.replace('/'+cliente+'/', '')
                dir_aux = dirname.split(os.sep)[1]
                zipado.write(
                    dirname + os.sep + filename,
                    "{}{}{}".format(dir_aux, os.sep, filename),
                    zipfile.ZIP_DEFLATED)
                # print('Armazenando arquivo '+ dir_aux + '/'+ filename )
                # print('Armazenando arquivo '+ dirname + os.sep + filename )
        zipado.close()

    def run_startup(self, script):
        # os.popen(script)
        # subprocess.Popen( script, shell=True, stdout=None, stderr=None )
        newpid = os.fork()
        if newpid == 0:
            os.execl(script, (""))
            sys.exit(0)
        # else:
        #    print("Entrou no ELSE...")

    def start(self, base):
        lista = glob(os.path.join('*', base, 'startup.sh'))
        if len(lista) == 0:
            self.write('Nao achou script')
            return
        script = lista[0]
        # p = Process( target=run_startup, args=script )
        # p.start()
        self.run_startup(script)
        self.write("Base {} iniciando...".format(base))

    def addInfo(self):
        options = self.ask_parameters()
        options['pastalocal'] = os.path.join(
            DIRETORIO_PADRAO, options.get('cliente'), options.get('base'))
        options['iengine'] = os.path.join(
            options.get('pastalocal'), 'iengine.exe')
        self.criar_arquivo_configuracao(options)
        self.create_startup(options)

#########################################################
#               OBJETO DE INTERAÇÃO C/ USUARIO          #
#########################################################


class Program(Cmd):
    def __init__(self):
        Cmd.__init__(self)
        self.admin = CacheAdmin()
        # self.intro          = MENSAGEM_INICIAL
        self.prompt = PROMPT
        self.doc_header = 'Comandos documentados'
        self.undoc_header = 'Comandos não documentados'
        self.ruler = '-'  # caractere usado na linha do header do help

    def do_shell(self, line):
        # print("Comando do shell:"+ line)
        output = os.popen(line).read()
        self.admin.write(output)
        self.last_output = output

    def help_shell(self):
        self.admin.write("\033[1;34mExecuta comandos do shell(Atalho = '!')")
        self.admin.write("Exemplo(no linux):")
        self.admin.write(">>> ! clear\t(Limpa a tela)")
        self.admin.write(">>> ! mkdir\t(Cria um diretorio)")
        self.admin.write(
            ">>> shell ls\t(Lista o conteúdo do diretório)\033[1;m")

    def do_lista(self, arg):
        try:
            self.do_shell("clear")
            self.admin.list_bases(arg.upper())
        except:
            print("Erro ao listar:\n" + traceback.format_exc())

    def help_lista(self):
        self.admin.write(
            "\033[1;34mLista as bases existentes informando, data de último acesso, espaço em disco utilizado e se a base está online.\033[1;m")

    def complete_lista(self, text, line, idxIni, idxFim):
        # return [c for c in self.admin.clientes if c.startswith(text.upper())]
        return self.admin.get_autocomplete_clientes(text)

    def do_cria(self, arg):
        try:
            options = None
            if arg:
                options = {}
                arglist = arg.split()
                optlist = getopt.getopt(
                    arglist, None, ['cliente=', 'url=', 'base='])[0]
                for op, value in optlist:
                    op = op.replace('-', '')
                    options[op] = value
            self.admin.criar_base(options)
        except:
            self.admin.write(
                "\033[1;31mErro\033[1;m:\n" + traceback.format_exc())

    def help_cria(self):
        self.admin.write("\033[1;34mCriação do cache local de uma base.")
        self.admin.write(
            "Exemplo: cria --cliente=CAFAZ --base=DCAFAZ --url=200.253.7.36:84")
        self.admin.write("Pode-se chamar sem nenhum parametro.")
        self.admin.write(
            "Nesse caso os dados serão solicitados ao usuário.\033[1;m")

    def do_descarta(self, arg):
        try:
            if not arg:
                self.admin.write("Utilização: descarta [chave | cache] BASE")
                return
            arglist = arg.split()
            if arglist[0] == 'cache':
                self.admin.write(
                    "Descartando cache da base {}".format(arglist[1]))
                self.admin.descartar_cache(arglist[1].upper())
            if arglist[0] == 'chave':
                self.admin.write(
                    "Descartando cache de chaves da base {}".format(arglist[1]))
                self.admin.descartar_chave(arglist[1].upper())
            if arglist[0] == 'base':
                self.admin.write(
                    "Descartando completamente a base {}".format(arglist[1]))
                self.admin.descartar_base(arglist[1].upper())
        except:
            self.admin.write("Ocorreu um erro:\n" + traceback.format_exc())

    def help_descarta(self):
        self.admin.write(
            "\033[1;34mDescarta o cache de dados, de chaves ou uma base inteira.")
        self.admin.write("Exemplos:")
        self.admin.write("\t>>>descarta cache DCASF")
        self.admin.write("\t>>>descarta chave HCASF")
        self.admin.write("\t>>>descarta base DCAFAZ\033[1;m")

    def do_pinga(self, arg):
        try:
            self.admin.verifica_disponibilidade(arg)
        except:
            self.admin.write("Erro:\n" + traceback.format_exc())

    def help_pinga(self):
        self.admin.write("\033[1;34mVerifica se uma base está online.")
        self.admin.write("Exemplo: pinga DESENVOLVE\033[1;m")

    def complete_pinga(self, text, line, idxIni, idxFim):
        # return [b for b in self.admin.bases if b.startswith(text.upper())]
        return self.admin.get_autocomplete_bases(text)

    def do_info(self, line):
        try:
            self.admin.info(line.upper())
        except:
            self.admin.write("Erro:\n" + traceback.format_exc())

    def help_info(self):
        self.admin.write("\033[1;34mInformações da base.\033[1;m")

    def complete_info(self, text, line, idxIni, idxFim):
        # return [b for b in self.admin.bases if b.startswith(text.upper())]
        return self.admin.get_autocomplete_bases(text)

    def do_start(self, basename):
        try:
            self.admin.start(basename.upper())
        except:
            self.admin.write("Erro..." + traceback.format_exc())

    def help_start(self):
        self.admin.write("\033[1;34mStarta uma base\033[1;m")

    def complete_start(self, text, line, idxIni, idxFim):
        # return [ b for b in self.admin.bases if b.startswith(text.upper())]
        return self.admin.get_autocomplete_bases(text)

    def do_backup(self, args):
            # TODO - testar se sao diretorios validos
        try:
            l = args.split()
            base = l[0]
            if len(l) == 1:
                destino = DIRETORIO_PADRAO_BACKUP
            else:
                destino = l[1]
            self.admin.write("Iniciando backup da base " + base + "...")
            self.admin.backup(base.upper(), destino)
        except:
            self.admin.write("Erro:\n" + traceback.format_exc())

    def help_backup(self):
        self.admin.write(
            "\033[1;34mCompacta a pasta da base informada e coloca no diretorio especificado.")
        self.admin.write("Exemplo: backup CASECH /home/ricardo/tmp/\033[1;m")

    def complete_backup(self, text, line, idxIni, idxFim):
        # return [b for b in self.admin.bases if b.startswith(text.upper())]
        return self.admin.get_autocomplete_bases(text)

    def do_addinfo(self, args):
        try:
            self.admin.addInfo()
        except:
            self.admin.write("Erro:\n" + traceback.format_exc())

    def help_addinfo(self):
        self.admin.write('\033[1;34mAdiciona as informações em uma base.')
        self.admin.write(
            'Esse comando irá solicitar os dados da base e irá criar os arquivos "base.cfg" e "startup.sh"')
        self.admin.write(
            'Útil quando você copia uma base de outro desenvolvedor.\033[1;m"')

    def complete_addinfo(self, text, line, idxIni, idxFim):
        return self.admin.get_autocomplete_bases(text)

    def help_help(self):
        self.admin.write("\033[1;34mExemplos:")
        self.admin.write(">>> help\t(Exibe a lista de comandos)")
        self.admin.write(">>> ?\t\t(Exibe a lista de comandos)")
        self.admin.write(">>> help help\t(Exibe essa ajuda)")
        self.admin.write(">>> help lista\t(Exibe a ajuda do comando 'lista')")
        self.admin.write(
            ">>> ? info\t(Exibe a ajuda do comando 'info')\033[1;m")

    def default(self, line):
        self.admin.write("\033[1;31mNao encontrado\033[1;m")

    def emptyline(self):
        pass

    def preloop(self):
        self.do_shell('echo "\033]0;"DYAD \& Associados"\007"')
        self.do_shell("clear")
        # self.admin.write('preloop')

    def postloop(self):
        self.admin.write('\nObrigado e volte sempre ;D')

    def do_EOF(self, line):
        return True

    def help_EOF(self):
        self.admin.write("\033[1;34mTecle CTRL+D para sair\033[1;m")

if __name__ == "__main__":
    Program().cmdloop()
