import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import tacoma as tc
#from tacoma.analysis import plot_contact_durations
from util import plot_contact_durations
from tacoma.analysis import plot_degree_distribution
import random
import human_mobility_networks as hm
from scipy.sparse import csr_array


# helper functions for loading saving networks, normalization and splitting them up into daily chunks
def normalized_nodes_time(df, tscale=20):
    nodes = np.union1d(df.i.unique(), df.j.unique())
    nodes_map = dict(zip(nodes, np.arange(len(nodes))))
    df.i = df.i.map(nodes_map)
    df.j = df.j.map(nodes_map)
    df.t = ((df.t - df.t.min())/20).astype('int')
    
    return df


def collect_SFHH():
    path = './data_eval/SFHH-conf-sensor.edges'
    df = pd.read_csv(path, names=['i', 'j', 't'])
    df['date'] = pd.to_datetime(df.t, unit='s')
    df['day'] = df.date.dt.date
    df = normalized_nodes_time(df)


    for grp, x in df.groupby('day'):
        x.t = x.t - x.t.min()
        x.to_parquet(f'./data_eval_split/SFHH/{grp}.parquet')


def collect_InVS():
    files = ['tij_InVS.dat', 'tij_InVS15.dat']
    path = './data_eval/'

    for i, file in enumerate(files):
        df = pd.read_csv(path + file, sep=' ', names=['t', 'i', 'j', 'Ci', 'Cj'])
        df['date'] = pd.to_datetime(df.t, unit='s')
        df['day'] = df.date.dt.date
        df = normalized_nodes_time(df)
        
        for grp, x in df.groupby('day'):
            x.t = x.t - x.t.min()
            x.to_parquet(f'./data_eval_split/InVS/f{i}_{grp}.parquet')


def collect_primaryschool():
    path = './data_eval/primaryschool.csv'
    df = pd.read_csv(path, sep='\t', names=['t', 'i', 'j', 'Ci', 'Cj'])
    df['date'] = pd.to_datetime(df.t, unit='s')
    df['day'] = df.date.dt.date
    df = normalized_nodes_time(df)

    for grp, x in df.groupby('day'):
            x.t = x.t - x.t.min()
            x.to_parquet(f'./data_eval_split/primaryschool/{grp}.parquet')


def collect_supermarket():
    files = ['wed17_1516.csv', 'thu25_1516.csv', 'thu25_1617.csv', 'fri19_1516.csv', 'fri26_1516.csv']
    path = './data_eval/'

    return [pd.read_csv(path + file) for file in files]


def collect_gallery():
    path = './data_eval/infectious/'

    for i, file in enumerate(os.listdir(path)):
        df = pd.read_csv(path + file, sep='\t', names=['t', 'i', 'j'])
        df['date'] = pd.to_datetime(df.t, unit='s')
        df['day'] = df.date.dt.date 
        df = normalized_nodes_time(df)   

        df.to_parquet(f'./data_eval_split/gallery/f{i}_{df.loc[0].day}.parquet')   


def collect_highschool():
    files = ['High-School_data_2013.csv', 'thiers_2012.csv', 'thiers_2011.csv']
    path = './data_eval/'

    for i, file in enumerate(files):
        if i == 0:
            sep = ' '
        else:
            sep = '\t'

        df = pd.read_csv(path + file, sep=sep, names=['t', 'i', 'j', 'Ci', 'Cj'])
        df['date'] = pd.to_datetime(df.t, unit='s')
        df['day'] = df.date.dt.date
        df = normalized_nodes_time(df)

        for grp, x in df.groupby('day'):
            x.t = x.t - x.t.min()
            x.to_parquet(f'./data_eval_split/highschool/f{i}_{grp}.parquet')


class EvaluationNetwork:
    def __init__(self, name, path=None):
        self.name = name

        # Load pandas DataFrame
        if path:
            self.df = pd.read_parquet(path)
            self.name_identifier = os.path.basename(path).split('.')[0]  # Splite filename from base path

        else:
            # No path provided -> choose a random file in the directory corresponding to name
            dirs = os.listdir(f'./data_eval_split/{self.name}')
            file = random.choice(dirs)
            self.df = pd.read_parquet(f'./data_eval_split/{self.name}/{file}')
            self.name_identifier = file.split('.')[0]


    def to_tacoma_tn(self):
        tn = tc.edge_lists()
        tn.N = max(self.df.i.max(), self.df.j.max()) + 1
        Nt = self.df.t.max() + 1
        tn.t = list(range(Nt))
        tn.tmax = Nt
        tn.time_unit = '20s'

        contacts = [[] for _ in range(Nt)]

        for _, contact in self.df.iterrows():
            contacts[contact.t].append([contact.i, contact.j])
        
        # Check for errors and convert to edge_changes
        tn.edges = contacts
        print('edge list errors: ', tc.verify(tn))

        tn = tc.convert(tn)
        print('edge changes errors: ', tc.verify(tn))
        self.tn = tn
    
    
    def eval_df_to_trajectory(self, switch_off_time):
        ij = np.hstack((self.df.i.values, self.df.j.values))
        tt = np.hstack((self.df.t.values, self.df.t.values))
        df2 = pd.DataFrame(data={'ij': ij, 'tt': tt})

        # Group by the 'i' column and aggregate the 't' values into a sorted list
        contacts = df2.groupby('ij')['tt'].apply(lambda x: np.array(sorted(x))).reset_index()
        p_id, activity_start_min, activity_end_min = [], [], []

        for _, person_contact in contacts.iterrows():
            switch_off_points = np.where(np.diff(person_contact.tt) >= switch_off_time)[0] 
            switch_off_points = np.insert(switch_off_points, [0, len(switch_off_points)], [-1, len(person_contact.tt) - 1])

            # Generate trajectories
            for _, (sonp, sofp) in enumerate(zip(switch_off_points[:-1], switch_off_points[1:])):
                p_id.append(person_contact.ij)
                activity_start_min.append(person_contact.tt[sonp + 1])
                activity_end_min.append(person_contact.tt[sofp])
            
        self.df = pd.DataFrame({'p_id': p_id, 'activity_start_min': activity_start_min, 'activity_end_min': activity_end_min})
        return self.df
    
    def hm_approximation(self, Loc, method, time_resotlution):
        print(self.df)
        self.method = method
        ts, te = self.df.activity_start_min.min(), self.df.activity_end_min.max() 
        HM = hm.HumanMobilityNetwork(self.df, Loc, ts, te, 20, 20)
        HM.make_movement(method=method)
        print('finished simulation \nstart working on network')

        self.tn_approx = HM.make_tacoma_network(1.5, time_resotlution)
            

    def overview_plots(self, approx):
        if approx:
            networks = [self.tn, self.tn_approx]
        else:
            networks = [self.tn]
        
        labels = [['contact', 'inter contact'], ['model contact', 'model inter contact']]
        colors = ['#1f77b4', '#ff7f0e']
        labels2 = ['data', 'model']

        fig, axs = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'{self.name} {self.name_identifier}')
        (ax1, ax2, ax3, ax4) = axs.flatten()
        for i, tn in enumerate(networks):
            ax1.set_title('contact duration distribution')
            plot_contact_durations(tc.api.measure_group_sizes_and_durations(tn), (ax1, ax3), fit_power_law=True, bins=100, xlabel='duration [min]', color=colors[i], label=labels[i])

            ax2.set_title('time average degreee distribution')
            plot_degree_distribution(tc.api.degree_distribution(tn), ax2, label=labels2[i])

            _, _, m = tc.edge_counts(tn)
            ax4.set_title('edge_counts')
            ax4.plot(tn.t, m[:-1], color=colors[i], label=labels2[i], alpha=.5)

            ax3.set_title('inter contact time distribution')

        for ax in axs.flatten():
            ax.legend()

        plt.tight_layout()
        plt.savefig(f'./plots/eval_networks/overview_{self.name}_{self.name_identifier}_approx_{approx}_{self.method}.png')
        plt.close()


if __name__ == '__main__':
    # path = './data_eval_split/gallery/f57_2009-07-04.parquet'
    EN = EvaluationNetwork('gallery')
    EN.to_tacoma_tn()
    # EN.overview_plots()
    EN.eval_df_to_trajectory(180)
    Loc = hm.Location(f'{EN.name}_{EN.name_identifier}', 3, 3, 10, 10)
    EN.hm_approximation(Loc, 'RWP', 20)

    EN.overview_plots(True)

    

